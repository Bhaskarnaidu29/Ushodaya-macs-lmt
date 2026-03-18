# savings.py - Member Savings Management with Security Deposit
from flask import Blueprint, render_template, request, redirect, url_for, flash, session, jsonify
from db import get_db_connection
from datetime import datetime
from decimal import Decimal
import traceback

savings_bp = Blueprint(
    "savings_bp",
    __name__,
    template_folder="templates"
)

# ═══════════════════════════════════════════════════════════════
#  HELPER: Calculate Member Balance
# ═══════════════════════════════════════════════════════════════
def get_member_balance(member_code, branchid=None):
    """Calculate total savings balance for a member"""
    conn = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        query = """
            SELECT 
                ISNULL(SUM(CASE WHEN credit_debit = 'Credit' THEN amount ELSE 0 END), 0) AS total_credit,
                ISNULL(SUM(CASE WHEN credit_debit = 'Debit' THEN amount ELSE 0 END), 0) AS total_debit
            FROM Savings
            WHERE member_code = ?
        """
        params = [member_code]
        
        if branchid:
            query += " AND Branchid = ?"
            params.append(branchid)
        
        cursor.execute(query, params)
        row = cursor.fetchone()
        
        if row:
            total_credit = Decimal(str(row[0] or 0))
            total_debit = Decimal(str(row[1] or 0))
            balance = total_credit - total_debit
            return balance
        return Decimal('0')
    
    except Exception:
        print(traceback.format_exc())
        return Decimal('0')
    finally:
        if conn:
            conn.close()


# ═══════════════════════════════════════════════════════════════
#  HELPER: Get Security Deposit Available for Withdrawal
# ═══════════════════════════════════════════════════════════════
def get_security_deposit_available(member_code):
    """Get security deposit amount available for withdrawal"""
    conn = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # Get closed/prepaid loans with unwithdrown security deposit
        cursor.execute("""
            SELECT 
                loanid,
                member_code,
                loanamount,
                securitydepositamount,
                ISNULL(securitydepositwithdrawn, 0) AS withdrawn,
                loanstatus
            FROM Loans
            WHERE member_code = ?
              AND loanstatus IN ('Closed', 'Prepaid', 'Settled')
              AND securitydepositamount > ISNULL(securitydepositwithdrawn, 0)
        """, (member_code,))
        
        loans = cursor.fetchall()
        return loans
    
    except Exception:
        print(traceback.format_exc())
        return []
    finally:
        if conn:
            conn.close()


# ═══════════════════════════════════════════════════════════════
#  API: Member Autocomplete
# ═══════════════════════════════════════════════════════════════
@savings_bp.route("/api/members")
def members_api():
    """Autocomplete search for members"""
    term = request.args.get("term", "").strip()
    if len(term) < 2:
        return jsonify([])
    
    conn = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("""
            SELECT TOP 10 member_code, full_name, phone1
            FROM Members
            WHERE member_code LIKE ? OR full_name LIKE ?
            ORDER BY full_name
        """, (f"%{term}%", f"%{term}%"))
        
        rows = cursor.fetchall()
        members = []
        for r in rows:
            members.append({
                "member_code": r[0] or "",
                "full_name": r[1] or "",
                "phone": r[2] or ""
            })
        return jsonify(members)
    
    except Exception:
        print(traceback.format_exc())
        return jsonify([]), 500
    finally:
        if conn:
            conn.close()


# ═══════════════════════════════════════════════════════════════
#  API: Get Member Balance
# ═══════════════════════════════════════════════════════════════
@savings_bp.route("/api/balance/<member_code>")
def get_balance_api(member_code):
    """Get current savings balance for a member"""
    branchid = session.get("branchid")
    balance = get_member_balance(member_code, branchid)
    
    # Get security deposit available
    sd_loans = get_security_deposit_available(member_code)
    total_sd = sum(
        Decimal(str(loan[3] or 0)) - Decimal(str(loan[4] or 0))
        for loan in sd_loans
    )
    
    return jsonify({
        "balance": float(balance),
        "security_deposit_available": float(total_sd),
        "loans_count": len(sd_loans)
    })


# ═══════════════════════════════════════════════════════════════
#  ROUTE: Savings Dashboard (List + Add)
# ═══════════════════════════════════════════════════════════════
@savings_bp.route("/", methods=["GET", "POST"])
def savings_dashboard():
    """Main savings dashboard with deposit/withdrawal form"""
    
    # Filters
    member_filter = request.args.get("member_code", "").strip()
    type_filter = request.args.get("type", "All").strip()
    
    # Initialize variables
    transactions = []
    total_credit = 0
    total_debit = 0
    balance = 0
    
    # ══════════════════════════════════════════════════════════
    #  POST - ADD TRANSACTION
    # ══════════════════════════════════════════════════════════
    if request.method == "POST" and request.form.get("action") == "add_transaction":
        conn = None
        try:
            member_code = request.form.get("member_code", "").strip()
            amount_raw = request.form.get("amount", "0")
            credit_debit = request.form.get("credit_debit", "Credit")
            savingtype = request.form.get("savingtype", "Regular Savings")
            transaction_date = request.form.get("transaction_date")
            
            if not member_code:
                flash("Member code is required", "danger")
                return redirect(url_for("savings_bp.savings_dashboard"))
            
            try:
                amount = Decimal(amount_raw)
                if amount <= 0:
                    raise ValueError("Amount must be positive")
            except:
                flash("Invalid amount", "danger")
                return redirect(url_for("savings_bp.savings_dashboard"))
            
            # Check balance for withdrawal
            if credit_debit == "Debit":
                current_balance = get_member_balance(member_code, session.get("branchid"))
                if amount > current_balance:
                    flash(f"Insufficient balance. Available: ₹{current_balance:,.2f}", "danger")
                    return redirect(url_for("savings_bp.savings_dashboard"))
            
            if not transaction_date:
                transaction_date = datetime.now()
            else:
                transaction_date = datetime.strptime(transaction_date, "%Y-%m-%d")
            
            branchid = int(session.get("branchid", 1))
            created_by = session.get("emp_name", "System")
            
            conn = get_db_connection()
            cursor = conn.cursor()
            
            # Insert transaction
            cursor.execute("""
                INSERT INTO Savings (
                    member_code, amount, credit_debit, savingtype,
                    transactiondate, Branchid, createdby, createddate,
                    interestcalculated
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, GETDATE(), 0)
            """, (
                member_code, str(amount), credit_debit, savingtype,
                transaction_date, branchid, created_by
            ))
            
            conn.commit()
            
            action_text = "deposited" if credit_debit == "Credit" else "withdrawn"
            flash(f"✅ ₹{amount:,.2f} {action_text} successfully!", "success")
            
            return redirect(url_for("savings_bp.savings_dashboard", member_code=member_code))
        
        except Exception as e:
            if conn:
                conn.rollback()
            flash(f"Error: {str(e)}", "danger")
            print(traceback.format_exc())
            return redirect(url_for("savings_bp.savings_dashboard"))
        finally:
            if conn:
                conn.close()
    
    # ══════════════════════════════════════════════════════════
    #  GET - LIST TRANSACTIONS
    # ══════════════════════════════════════════════════════════
    conn = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # Build query
        query = """
            SELECT 
                s.membersavingid,
                s.member_code,
                m.full_name,
                s.amount,
                s.credit_debit,
                s.savingtype,
                s.transactiondate,
                s.createdby,
                s.createddate
            FROM Savings s
            LEFT JOIN Members m ON s.member_code = m.member_code
            WHERE 1=1
        """
        params = []
        
        # Branch filter
        branchid = session.get("branchid")
        if branchid:
            query += " AND s.Branchid = ?"
            params.append(branchid)
        
        # Member filter
        if member_filter:
            query += " AND s.member_code = ?"
            params.append(member_filter)
        
        # Type filter
        if type_filter != "All":
            query += " AND s.credit_debit = ?"
            params.append(type_filter)
        
        query += " ORDER BY s.transactiondate DESC, s.createddate DESC"
        
        cursor.execute(query, params)
        transactions = cursor.fetchall()
        
        # Calculate totals
        total_credit = sum(float(t[3] or 0) for t in transactions if t[4] == "Credit")
        total_debit = sum(float(t[3] or 0) for t in transactions if t[4] == "Debit")
        balance = total_credit - total_debit
    
    except Exception:
        flash("Error loading transactions", "danger")
        print(traceback.format_exc())
    finally:
        if conn:
            conn.close()
    
    return render_template(
        "savings.html",
        transactions=transactions,
        member_filter=member_filter,
        type_filter=type_filter,
        total_credit=total_credit,
        total_debit=total_debit,
        balance=balance,
        today=datetime.now().strftime("%Y-%m-%d")
    )


# ═══════════════════════════════════════════════════════════════
#  ROUTE: Withdraw Security Deposit
# ═══════════════════════════════════════════════════════════════
@savings_bp.route("/withdraw-security-deposit", methods=["GET", "POST"])
def withdraw_security_deposit():
    """Withdraw security deposit from closed loans"""
    
    if request.method == "POST":
        conn = None
        try:
            loan_id = request.form.get("loan_id")
            member_code = request.form.get("member_code")
            amount_raw = request.form.get("amount", "0")
            
            if not loan_id or not member_code:
                flash("Loan ID and Member Code required", "danger")
                return redirect(url_for("savings_bp.withdraw_security_deposit"))
            
            try:
                amount = Decimal(amount_raw)
                if amount <= 0:
                    raise ValueError("Amount must be positive")
            except:
                flash("Invalid amount", "danger")
                return redirect(url_for("savings_bp.withdraw_security_deposit"))
            
            conn = get_db_connection()
            cursor = conn.cursor()
            
            # Verify loan status and available security deposit
            cursor.execute("""
                SELECT 
                    securitydepositamount,
                    ISNULL(securitydepositwithdrawn, 0) AS withdrawn,
                    loanstatus
                FROM Loans
                WHERE loanid = ? AND member_code = ?
            """, (loan_id, member_code))
            
            loan = cursor.fetchone()
            if not loan:
                flash("Loan not found", "danger")
                return redirect(url_for("savings_bp.withdraw_security_deposit"))
            
            sd_amount = Decimal(str(loan[0] or 0))
            sd_withdrawn = Decimal(str(loan[1] or 0))
            loan_status = loan[2]
            
            if loan_status not in ['Closed', 'Prepaid', 'Settled']:
                flash("Security deposit can only be withdrawn for closed/prepaid loans", "danger")
                return redirect(url_for("savings_bp.withdraw_security_deposit"))
            
            available = sd_amount - sd_withdrawn
            if amount > available:
                flash(f"Amount exceeds available security deposit: ₹{available:,.2f}", "danger")
                return redirect(url_for("savings_bp.withdraw_security_deposit"))
            
            # Record withdrawal in Savings as Credit
            branchid = int(session.get("branchid", 1))
            created_by = session.get("emp_name", "System")
            
            cursor.execute("""
                INSERT INTO Savings (
                    member_code, loanid, amount, credit_debit, savingtype,
                    transactiondate, Branchid, createdby, createddate,
                    interestcalculated
                )
                VALUES (?, ?, ?, 'Credit', 'Security Deposit Return', 
                        GETDATE(), ?, ?, GETDATE(), 0)
            """, (member_code, loan_id, str(amount), branchid, created_by))
            
            # Update Loans table
            cursor.execute("""
                UPDATE Loans
                SET securitydepositwithdrawn = ISNULL(securitydepositwithdrawn, 0) + ?,
                    modifiedby = ?,
                    modifieddate = GETDATE()
                WHERE loanid = ?
            """, (str(amount), int(session.get("user_id", 1)), loan_id))
            
            conn.commit()
            flash(f"✅ Security deposit of ₹{amount:,.2f} credited to member account!", "success")
            
            return redirect(url_for("savings_bp.withdraw_security_deposit", member_code=member_code))
        
        except Exception as e:
            if conn:
                conn.rollback()
            flash(f"Error: {str(e)}", "danger")
            print(traceback.format_exc())
            return redirect(url_for("savings_bp.withdraw_security_deposit"))
        finally:
            if conn:
                conn.close()
    
    # GET - Show security deposit withdrawal form
    member_code = request.args.get("member_code", "").strip()
    loans_with_sd = []
    
    if member_code:
        loans_with_sd = get_security_deposit_available(member_code)
    
    return render_template(
        "security_deposit.html",
        member_code=member_code,
        loans=loans_with_sd
    )
