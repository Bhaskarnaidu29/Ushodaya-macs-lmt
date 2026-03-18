# 🚀 COMPLETE DEPLOYMENT PACKAGE - ALL 4 REQUIREMENTS

## 📋 **REQUIREMENTS IMPLEMENTED:**

1. ✅ **Advance Recovery Integration** - Dropdown (Cash/Advance)
2. ✅ **Undo Recovery** - Admin/Manager only
3. ✅ **Undo Recovery** - Only after DayEnd table date
4. ✅ **Payment Mode Dropdown** - Cash default, Advance only if balance exists

---

## 📦 **FILES PROVIDED:**

### **1. loanrec_main_WITH_ADVANCE_DROPDOWN.html** ⭐⭐⭐
- ✅ Payment Mode dropdown column
- ✅ Shows "Cash/Advance" if member has advance balance
- ✅ Shows "Cash Only" if no advance
- ✅ Auto-updates amounts based on selection
- ✅ Visual feedback (green background for advance)

### **2. advance.py** (Already have)
- ✅ Manual advance application only
- ✅ Balance checking
- ✅ Credit/Debit tracking

### **3. CODE CHANGES FOR loanrec.py**
- ✅ Import advance functions
- ✅ Get advance balances
- ✅ Handle payment_mode dropdown
- ✅ Undo recovery function
- ✅ Permission checks (admin/manager)
- ✅ DayEnd date validation

---

## 🔧 **STEP 1: Deploy HTML Template**

```bash
cd "D:\Software\UD Lms 23022026\UD Lms 23022026\UD Lms\templates"

# Backup
copy loanrec_main.html loanrec_main_OLD.html

# Deploy
copy loanrec_main_WITH_ADVANCE_DROPDOWN.html loanrec_main.html
```

---

## 🔧 **STEP 2: Update loanrec.py**

### **ADD AT TOP (after imports, line ~8):**

```python
# ═══════════════════════════════════════════════════════════════════════════
# IMPORT ADVANCE FUNCTIONS
# ═══════════════════════════════════════════════════════════════════════════
try:
    from advance import get_advance_balance
    ADVANCE_ENABLED = True
except ImportError:
    ADVANCE_ENABLED = False
    print("WARNING: Advance module not found.")
```

---

### **ADD HELPER FUNCTION (after _close_loan_if_done, line ~30):**

```python
def _apply_advance_manually(cursor, member_code, loanid, loanrecid, amount_needed, user_id):
    """
    Manually apply advance to LoanRec EMI.
    Called when payment_mode = 'advance'
    
    Returns: (amount_applied, new_balance)
    """
    if not ADVANCE_ENABLED:
        return (Decimal('0'), Decimal('0'))
    
    try:
        balance = get_advance_balance(member_code, loanid)
        
        if balance <= 0:
            return (Decimal('0'), Decimal('0'))
        
        amount_to_apply = min(balance, amount_needed)
        
        if amount_to_apply <= 0:
            return (Decimal('0'), balance)
        
        # Update LoanRec.advancerecovery
        cursor.execute("""
            UPDATE LoanRec
            SET advancerecovery = ISNULL(advancerecovery, 0) + ?,
                modifiedby = ?,
                modifieddate = GETDATE()
            WHERE loanrecid = ?
        """, (float(amount_to_apply), user_id, loanrecid))
        
        # Insert Debit entry in AdvanceRecovery
        cursor.execute("""
            INSERT INTO AdvanceRecovery (
                member_code, loanid, amount, creditdebit, notes,
                createdby, createddate, transactiondate
            )
            VALUES (?, ?, ?, 'Debit', ?, ?, GETDATE(), GETDATE())
        """, (
            member_code, loanid, float(amount_to_apply),
            f"Auto-applied via recovery posting to LoanRec #{loanrecid}",
            user_id
        ))
        
        new_balance = get_advance_balance(member_code, loanid)
        return (amount_to_apply, new_balance)
        
    except Exception as e:
        print(f"Error applying advance: {str(e)}")
        return (Decimal('0'), Decimal('0'))


def _can_undo_recovery(cursor, loanrecid, role):
    """
    Check if recovery can be undone.
    
    Rules:
    1. Only Admin or Manager can undo
    2. Can only undo if recovery date is AFTER latest DayEnd date
    
    Returns: (can_undo, message)
    """
    # Check role
    if role not in ['Admin', 'Manager']:
        return (False, "Only Admin and Manager can undo recovery")
    
    # Get recovery date
    cursor.execute("""
        SELECT modifieddate, duedate
        FROM LoanRec
        WHERE loanrecid = ?
    """, (loanrecid,))
    
    rec = cursor.fetchone()
    if not rec:
        return (False, "LoanRec not found")
    
    recovery_date = rec[0] or rec[1]
    
    if not recovery_date:
        return (False, "No recovery date found")
    
    # Get latest DayEnd date
    cursor.execute("""
        SELECT TOP 1 dayenddate
        FROM DayEnd
        ORDER BY dayenddate DESC
    """)
    
    dayend = cursor.fetchone()
    
    if dayend and dayend[0]:
        dayend_date = dayend[0]
        
        # Can only undo if recovery is AFTER dayend
        if recovery_date <= dayend_date:
            return (False, f"Cannot undo: Recovery is before DayEnd ({dayend_date.strftime('%d %b %Y')})")
    
    return (True, "Can undo")
```

---

### **UPDATE recovery_posting() function:**

**FIND** (around line 52):
```python
members     = []
center_info = None
```

**ADD AFTER:**
```python
advance_balances = {}  # {member_code: {loanid: balance}}
```

---

**FIND** (around line 91, after `members = c.fetchall()`):

**ADD AFTER:**
```python
# Get advance balances for all members
if ADVANCE_ENABLED and members:
    for m in members:
        member_code = m[0]
        loanid = m[2]
        
        if member_code not in advance_balances:
            advance_balances[member_code] = {}
        
        if loanid not in advance_balances[member_code]:
            balance = get_advance_balance(member_code, loanid)
            advance_balances[member_code][loanid] = float(balance)
```

---

**FIND** (in POST processing, around line 108, inside the loop):
```python
for loanrecid in selected_members:
    principal        = Decimal(str(request.form.get(f"principal_{loanrecid}",  0) or 0))
    interest         = Decimal(str(request.form.get(f"interest_{loanrecid}",   0) or 0))
    savings          = Decimal(str(request.form.get(f"savings_{loanrecid}",    0) or 0))
    addl_due         = Decimal(str(request.form.get(f"addl_due_{loanrecid}",   0) or 0))
    extra_addl       = Decimal(str(request.form.get(f"extra_addl_{loanrecid}", 0) or 0))
    additional_sav   = addl_due + extra_addl
```

**ADD AFTER:**
```python
# Get payment mode (cash or advance)
payment_mode = request.form.get(f"payment_mode_{loanrecid}", "cash")
```

---

**FIND** (around line 133, after getting rec details):
```python
i_due       = float(rec[3] or 0)

is_fully_paid = (float(principal) >= p_due and float(interest) >= i_due)
```

**REPLACE WITH:**
```python
i_due       = float(rec[3] or 0)

# ═══════════════════════════════════════════════════════════════
# HANDLE ADVANCE PAYMENT MODE
# ═══════════════════════════════════════════════════════════════
advance_applied = Decimal('0')
cash_payment = principal + interest + savings + additional_sav

if payment_mode == 'advance' and ADVANCE_ENABLED:
    # Member selected advance payment
    total_due = Decimal(str(p_due)) + Decimal(str(i_due))
    
    # Apply advance to cover the EMI
    advance_applied, new_balance = _apply_advance_manually(
        c, member_code, loanid, loanrecid, total_due, user_id
    )
    
    if advance_applied > 0:
        # Allocate advance to principal/interest
        remaining_advance = advance_applied
        
        # Priority: Interest → Principal
        advance_to_interest = min(remaining_advance, Decimal(str(i_due)))
        if advance_to_interest > 0:
            interest += advance_to_interest
            remaining_advance -= advance_to_interest
        
        advance_to_principal = min(remaining_advance, Decimal(str(p_due)))
        if advance_to_principal > 0:
            principal += advance_to_principal
            remaining_advance -= advance_to_principal

is_fully_paid = (float(principal) >= p_due and float(interest) >= i_due)
```

---

**FIND** (around line 200, flash message):
```python
flash(
    f"Recovery posted! {posted_count} EMI(s) | "
    f"Total: ₹{float(total_collected):,.2f}",
    "success"
)
```

**REPLACE WITH:**
```python
msg = f"✅ Recovery posted! {posted_count} EMI(s) | Cash: ₹{float(total_collected):,.2f}"

# Track advance usage
total_advance = sum(
    Decimal(str(request.form.get(f"advance_used_{loanrecid}", 0) or 0))
    for loanrecid in selected_members
)

if total_advance > 0:
    msg += f" | Advance: ₹{float(total_advance):,.2f}"

flash(msg, "success")
```

---

**FIND** (around line 220, return statement):
```python
return render_template("loanrec_main.html",
                       centers=centers,
                       members=members,
                       selected_center=selected_center,
                       center_info=center_info,
                       today=datetime.now().strftime('%d %b %Y'))
```

**REPLACE WITH:**
```python
return render_template("loanrec_main.html",
                       centers=centers,
                       members=members,
                       selected_center=selected_center,
                       center_info=center_info,
                       today=datetime.now().strftime('%d %b %Y'),
                       advance_balances=advance_balances,
                       advance_enabled=ADVANCE_ENABLED)
```

---

## 🔧 **STEP 3: Add Undo Recovery Route**

**ADD NEW ROUTE (at end of file, before if __name__):**

```python
# ═══════════════════════════════════════════════════════════════
# UNDO RECOVERY (Admin/Manager only, After DayEnd only)
# ═══════════════════════════════════════════════════════════════
@loanrec_bp.route("/undo/<int:loanrecid>", methods=["POST"])
def undo_recovery(loanrecid):
    """
    Undo a recovery posting.
    
    RESTRICTIONS:
    1. Only Admin or Manager can undo
    2. Can only undo if recovery date is AFTER latest DayEnd date
    """
    try:
        role = session.get("role", "")
        user_id = session.get("user_id", 1)
        
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # Check permissions
        can_undo, msg = _can_undo_recovery(cursor, loanrecid, role)
        
        if not can_undo:
            flash(f"❌ Cannot undo: {msg}", "danger")
            conn.close()
            return redirect(request.referrer or url_for("loanrec.recovery_posting"))
        
        # Get LoanRec details before undoing
        cursor.execute("""
            SELECT 
                lr.loanid,
                l.member_code,
                lr.principalpaidamount,
                lr.interestpaidamount,
                lr.savingspaidamount,
                lr.advancerecovery,
                lr.emisequence
            FROM LoanRec lr
            JOIN Loans l ON lr.loanid = l.loanid
            WHERE lr.loanrecid = ?
        """, (loanrecid,))
        
        rec = cursor.fetchone()
        
        if not rec:
            flash("LoanRec not found", "danger")
            conn.close()
            return redirect(request.referrer or url_for("loanrec.recovery_posting"))
        
        loanid = rec[0]
        member_code = rec[1]
        principal_paid = float(rec[2] or 0)
        interest_paid = float(rec[3] or 0)
        savings_paid = float(rec[4] or 0)
        advance_used = float(rec[5] or 0)
        emisequence = rec[6]
        
        # Reverse LoanRec payment
        cursor.execute("""
            UPDATE LoanRec
            SET principalpaidamount = 0,
                interestpaidamount = 0,
                savingspaidamount = 0,
                advancerecovery = 0,
                paid = 0,
                modifiedby = ?,
                modifieddate = GETDATE()
            WHERE loanrecid = ?
        """, (user_id, loanrecid))
        
        # Reverse Loans outstanding
        cursor.execute("""
            UPDATE Loans
            SET principaloutstanding = principaloutstanding + ?,
                interestoutstanding = interestoutstanding + ?,
                modifiedby = ?,
                modifieddate = GETDATE()
            WHERE loanid = ?
        """, (principal_paid, interest_paid, user_id, loanid))
        
        # Reverse advance if used
        if advance_used > 0 and ADVANCE_ENABLED:
            # Delete the Debit entry (or insert Credit to reverse)
            cursor.execute("""
                INSERT INTO AdvanceRecovery (
                    member_code, loanid, amount, creditdebit, notes,
                    createdby, createddate, transactiondate
                )
                VALUES (?, ?, ?, 'Credit', ?, ?, GETDATE(), GETDATE())
            """, (
                member_code, loanid, advance_used,
                f"Undo recovery for LoanRec #{loanrecid}",
                user_id
            ))
        
        # Delete Savings transactions
        cursor.execute("""
            DELETE FROM Savings
            WHERE loanrecid = ?
              AND createddate >= (
                  SELECT TOP 1 dayenddate 
                  FROM DayEnd 
                  ORDER BY dayenddate DESC
              )
        """, (loanrecid,))
        
        conn.commit()
        cursor.close()
        conn.close()
        
        flash(
            f"✅ Recovery undone! EMI #{emisequence} | "
            f"Principal: ₹{principal_paid:,.2f} | "
            f"Interest: ₹{interest_paid:,.2f}" +
            (f" | Advance: ₹{advance_used:,.2f}" if advance_used > 0 else ""),
            "success"
        )
        
        return redirect(request.referrer or url_for("loanrec.recovery_posting"))
        
    except Exception as e:
        if 'conn' in locals():
            conn.rollback()
            conn.close()
        flash(f"Error undoing recovery: {str(e)}", "danger")
        return redirect(request.referrer or url_for("loanrec.recovery_posting"))
```

---

## 🔧 **STEP 4: Add Undo Button to View**

Create a new file `recovery_history.html` or add to existing view:

```html
<!-- Show in recovery list or individual view -->
{% if role in ['Admin', 'Manager'] %}
<form method="POST" action="{{ url_for('loanrec.undo_recovery', loanrecid=record.loanrecid) }}"
      onsubmit="return confirm('Undo this recovery? This will reverse all payments.')">
    <button type="submit" class="btn btn-sm btn-danger">
        <i class="bi bi-arrow-counterclockwise"></i> Undo
    </button>
</form>
{% endif %}
```

---

## 📋 **DEPLOYMENT CHECKLIST:**

```
☐ Step 1: Deploy loanrec_main_WITH_ADVANCE_DROPDOWN.html
☐ Step 2: Update loanrec.py with all code changes above
☐ Step 3: Add undo_recovery route to loanrec.py
☐ Step 4: Deploy advance.py (if not already done)
☐ Step 5: Add undo button to recovery views (optional)
☐ Step 6: Restart Flask
☐ Step 7: Test advance dropdown
☐ Step 8: Test undo recovery (admin login)
☐ Step 9: Test DayEnd restriction
```

---

## 🧪 **TESTING:**

### **Test 1: Advance Dropdown**
```
1. Post advance for member (₹5,000)
2. Go to recovery posting
3. Select member
4. See dropdown: "💵 Cash" / "💰 Advance"
5. Select "Advance"
6. Fields auto-fill to 0
7. Submit

Expected:
✅ "Cash: ₹0.00 | Advance: ₹1,500"
✅ Advance balance reduced
```

### **Test 2: Cash Only (No Advance)**
```
1. Member with no advance
2. See dropdown disabled: "💵 Cash Only"
3. Fill amounts manually
4. Submit

Expected:
✅ Normal cash payment
✅ No advance applied
```

### **Test 3: Undo Recovery (Admin)**
```
1. Login as Admin
2. Go to recovery
3. Post recovery for member
4. Click "Undo" button
5. Confirm

Expected:
✅ Recovery undone
✅ LoanRec reset to unpaid
✅ Advance balance restored
```

### **Test 4: Undo Restricted (Staff)**
```
1. Login as Staff
2. Try to undo recovery

Expected:
❌ "Only Admin and Manager can undo"
```

### **Test 5: Undo Restricted (Before DayEnd)**
```
1. Do DayEnd for today
2. Try to undo yesterday's recovery

Expected:
❌ "Cannot undo: Recovery is before DayEnd"
```

---

## 🎯 **FEATURES SUMMARY:**

### **1. Advance Recovery Integration** ✅
- Dropdown in recovery table
- Auto-shows for members with advance
- Cash only for members without advance
- Visual feedback (green background)

### **2. Undo Recovery** ✅
- Admin/Manager only
- After DayEnd restriction
- Reverses all payments
- Restores advance balance

### **3. Payment Mode Dropdown** ✅
- 💵 Cash (default)
- 💰 Advance (if balance available)
- Auto-fills amounts based on selection

### **4. DayEnd Protection** ✅
- Cannot undo before DayEnd date
- Protects finalized records
- Clear error messages

---

## 📦 **ALL FILES READY:**

```
Files to Deploy:
├── loanrec_main_WITH_ADVANCE_DROPDOWN.html → templates/loanrec_main.html
├── advance.py (already have)
└── loanrec.py (apply code changes above)
```

**DEPLOY ALL CHANGES FOR COMPLETE SYSTEM!** 🚀✨
