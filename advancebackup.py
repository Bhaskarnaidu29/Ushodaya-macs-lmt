"""
Advance Recovery Module - MANUAL APPLICATION ONLY
────────────────────────────────────────────────────────────────────────────
CRITICAL RULE:
  ❌ NO AUTO-DEDUCTION of advance
  ✅ Staff must MANUALLY apply advance during recovery posting
  ✅ Only when member is PRESENT and requests to use advance
  
WORKFLOW:
  1. Member pays advance → Store in AdvanceRecovery (Credit)
  2. Member comes for weekly collection
  3. Staff checks: "Do you want to use advance?"
  4. If YES → Staff manually applies advance
  5. If NO → Member pays cash
  6. If ABSENT → NO advance deduction (EMI remains unpaid)

WHY MANUAL ONLY:
  - Member may be absent/unable to pay
  - Auto-deduction would waste advance on non-attendance
  - Member should control when to use their advance
  - Staff confirms member is present before applying
────────────────────────────────────────────────────────────────────────────
"""
from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify, session
from datetime import datetime
from decimal import Decimal
from db import get_db_connection
from login import login_required

advance_bp = Blueprint("advance", __name__, template_folder="templates")


# ═════════════════════════════════════════════════════════════════════════
# HELPER FUNCTIONS
# ═════════════════════════════════════════════════════════════════════════

def get_advance_balance(member_code, loanid):
    """
    Calculate available advance balance.
    Balance = Credits (deposits) - Debits (used in recovery)
    """
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # Total credits
    cursor.execute("""
        SELECT ISNULL(SUM(amount), 0) 
        FROM AdvanceRecovery
        WHERE member_code = ? 
          AND loanid = ?
          AND creditdebit = 'Credit'
    """, (member_code, loanid))
    total_credit = Decimal(str(cursor.fetchone()[0] or 0))
    
    # Total debits
    cursor.execute("""
        SELECT ISNULL(SUM(amount), 0)
        FROM AdvanceRecovery
        WHERE member_code = ?
          AND loanid = ?
          AND creditdebit = 'Debit'
    """, (member_code, loanid))
    total_debit = Decimal(str(cursor.fetchone()[0] or 0))
    
    cursor.close()
    conn.close()
    
    balance = total_credit - total_debit
    return balance if balance > 0 else Decimal('0')


# ═════════════════════════════════════════════════════════════════════════
# ROUTES
# ═════════════════════════════════════════════════════════════════════════

@advance_bp.route("/", methods=["GET"])
@login_required
def list_advances():
    """Display all advance transactions."""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        cursor.execute("""
            SELECT 
                AR.advancerecoveryid,
                AR.member_code,
                M.full_name AS member_name,
                AR.loanid,
                AR.amount,
                AR.creditdebit,
                AR.notes,
                AR.transactiondate,
                AR.createdby,
                AR.createddate,
                AR.paymentid
            FROM AdvanceRecovery AR
            LEFT JOIN Members M ON AR.member_code = M.member_code
            ORDER BY AR.advancerecoveryid DESC
        """)
        
        advances = cursor.fetchall()
        cursor.close()
        conn.close()
        
        return render_template("advance.html", advances=advances)
        
    except Exception as e:
        flash(f"Error: {str(e)}", "danger")
        return redirect(url_for("dashboard.index"))


@advance_bp.route("/add", methods=["GET"])
@login_required
def show_add_advance_form():
    """Show form to post advance deposit."""
    return render_template("advance_add.html")


@advance_bp.route("/search_member", methods=["GET"])
@login_required
def search_member():
    """Search members for advance posting."""
    query = request.args.get("q", "").strip()
    
    if len(query) < 2:
        return jsonify([])
    
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        cursor.execute("""
            SELECT DISTINCT member_code, full_name
            FROM Members
            WHERE member_code LIKE ? OR full_name LIKE ?
            ORDER BY member_code
        """, (f"%{query}%", f"%{query}%"))
        
        results = [
            {"member_code": row[0], "full_name": row[1]}
            for row in cursor.fetchall()
        ]
        
        cursor.close()
        conn.close()
        
        return jsonify(results)
        
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@advance_bp.route("/get_loans/<member_code>")
@login_required
def get_loans(member_code):
    """Get active loans for member."""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        cursor.execute("""
            SELECT DISTINCT
                L.loanid,
                L.loanamount,
                L.principaloutstanding,
                L.disbursementdate,
                LP.ProductName
            FROM Loans L
            LEFT JOIN LoanProduct LP ON L.productid = LP.ProductID
            WHERE L.member_code = ?
              AND L.loanstatus = 'Active'
            ORDER BY L.loanid DESC
        """, (member_code,))
        
        results = [
            {
                "loanid": row[0],
                "loanamount": float(row[1] or 0),
                "outstanding": float(row[2] or 0),
                "disbursementdate": row[3].strftime('%d %b %Y') if row[3] else '',
                "product": row[4] or 'Unknown'
            }
            for row in cursor.fetchall()
        ]
        
        cursor.close()
        conn.close()
        
        return jsonify(results)
        
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@advance_bp.route("/add", methods=["POST"])
@login_required
def add_advance():
    """
    Post advance deposit.
    
    ═══════════════════════════════════════════════════════════════════════
    IMPORTANT: This ONLY saves deposit to AdvanceRecovery table.
    It does NOT update LoanRec or apply advance automatically.
    
    Advance is applied MANUALLY during recovery posting when:
    - Member is PRESENT at collection
    - Member REQUESTS to use advance
    - Staff manually selects "Use Advance" option
    ═══════════════════════════════════════════════════════════════════════
    """
    try:
        member_code = request.form.get("member_code", "").strip()
        loanid = request.form.get("loanid", "").strip()
        amount_str = request.form.get("amount", "0").strip()
        transactiondate_str = request.form.get("transactiondate", "").strip()
        paymentid = request.form.get("paymentid", "").strip() or None
        
        if not member_code or not loanid:
            flash("Member code and Loan ID required.", "warning")
            return redirect(url_for("advance.show_add_advance_form"))
        
        try:
            amount = Decimal(amount_str)
            if amount <= 0:
                raise ValueError("Amount must be positive")
        except (ValueError, Exception):
            flash("Invalid amount.", "warning")
            return redirect(url_for("advance.show_add_advance_form"))
        
        transactiondate = None
        if transactiondate_str:
            try:
                transactiondate = datetime.strptime(transactiondate_str, "%Y-%m-%dT%H:%M")
            except ValueError:
                transactiondate = datetime.now()
        else:
            transactiondate = datetime.now()
        
        user_id = session.get("user_id", 1)
        username = session.get("username", "system")
        
        # Insert CREDIT entry only
        conn = get_db_connection()
        cursor = conn.cursor()
        
        cursor.execute("""
            INSERT INTO AdvanceRecovery (
                member_code, loanid, amount, creditdebit, notes,
                createdby, createddate, transactiondate, paymentid
            )
            VALUES (?, ?, ?, 'Credit', ?, ?, GETDATE(), ?, ?)
        """, (
            member_code, loanid, float(amount),
            f"Advance deposit by {username}",
            user_id, transactiondate, paymentid
        ))
        
        conn.commit()
        
        new_balance = get_advance_balance(member_code, loanid)
        
        cursor.close()
        conn.close()
        
        flash(
            f"✅ Advance deposited! Amount: ₹{float(amount):,.2f} | "
            f"Available Balance: ₹{float(new_balance):,.2f} | "
            f"⚠️ Staff must manually apply during recovery posting!",
            "success"
        )
        
        return redirect(url_for("advance.list_advances"))
        
    except Exception as e:
        flash(f"Error: {str(e)}", "danger")
        return redirect(url_for("advance.show_add_advance_form"))


@advance_bp.route("/balance/<member_code>/<int:loanid>")
@login_required
def check_balance(member_code, loanid):
    """
    Check advance balance API.
    Used by recovery posting to show available balance to staff.
    """
    try:
        balance = get_advance_balance(member_code, loanid)
        
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT full_name FROM Members WHERE member_code = ?", (member_code,))
        result = cursor.fetchone()
        member_name = result[0] if result else None
        cursor.close()
        conn.close()
        
        return jsonify({
            "member_code": member_code,
            "member_name": member_name,
            "loanid": loanid,
            "balance": float(balance)
        })
        
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@advance_bp.route("/apply_manual", methods=["POST"])
@login_required
def apply_manual():
    """
    Manually apply advance to LoanRec EMI.
    
    ═══════════════════════════════════════════════════════════════════════
    CALLED BY: Recovery posting module when staff clicks "Use Advance"
    
    PREREQUISITES:
    - Member must be PRESENT
    - Member must REQUEST to use advance
    - Staff must manually confirm
    
    WORKFLOW:
    1. Check balance available
    2. Calculate amount to apply
    3. Update LoanRec.advancerecovery
    4. Insert Debit entry in AdvanceRecovery
    5. Return amount applied
    ═══════════════════════════════════════════════════════════════════════
    """
    try:
        data = request.get_json()
        member_code = data.get("member_code")
        loanid = data.get("loanid")
        loanrecid = data.get("loanrecid")
        amount_requested = Decimal(str(data.get("amount", 0)))
        
        if not all([member_code, loanid, loanrecid]) or amount_requested <= 0:
            return jsonify({"error": "Invalid parameters"}), 400
        
        # Check balance
        balance = get_advance_balance(member_code, loanid)
        
        if balance <= 0:
            return jsonify({
                "success": False,
                "message": "No advance balance available",
                "balance": 0
            })
        
        # Amount to apply (min of requested and available)
        amount_to_apply = min(balance, amount_requested)
        
        conn = get_db_connection()
        cursor = conn.cursor()
        user_id = session.get("user_id", 1)
        
        # Update LoanRec
        cursor.execute("""
            UPDATE LoanRec
            SET advancerecovery = ISNULL(advancerecovery, 0) + ?,
                modifiedby = ?,
                modifieddate = GETDATE()
            WHERE loanrecid = ?
        """, (float(amount_to_apply), user_id, loanrecid))
        
        # Insert Debit entry
        cursor.execute("""
            INSERT INTO AdvanceRecovery (
                member_code, loanid, amount, creditdebit, notes,
                createdby, createddate, transactiondate
            )
            VALUES (?, ?, ?, 'Debit', ?, ?, GETDATE(), GETDATE())
        """, (
            member_code, loanid, float(amount_to_apply),
            f"Manually applied to LoanRec #{loanrecid}",
            user_id
        ))
        
        conn.commit()
        
        new_balance = get_advance_balance(member_code, loanid)
        
        cursor.close()
        conn.close()
        
        return jsonify({
            "success": True,
            "applied": float(amount_to_apply),
            "balance": float(new_balance),
            "message": f"Applied ₹{float(amount_to_apply):,.2f} from advance"
        })
        
    except Exception as e:
        return jsonify({"error": str(e)}), 500
