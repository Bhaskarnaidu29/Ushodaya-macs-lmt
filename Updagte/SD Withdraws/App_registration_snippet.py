# ════════════════════════════════════════════════════════════
#  ADD THESE TWO LINES TO App.py
# ════════════════════════════════════════════════════════════

# --- Step 1: With the other imports (around line 92) ---
from SecurityDepositWithdraw import sd_withdraw_bp

# --- Step 2: With the other blueprint registrations (around line 116) ---
app.register_blueprint(sd_withdraw_bp, url_prefix="/sd_withdraw")


# ════════════════════════════════════════════════════════════
#  SQL: Create SecurityDepositLedger table (run once in SSMS)
#  The Python code also auto-creates it on first withdrawal,
#  but running this manually is safer for production.
# ════════════════════════════════════════════════════════════
"""
CREATE TABLE SecurityDepositLedger (
    id               INT IDENTITY(1,1) PRIMARY KEY,
    loanid           INT           NOT NULL,
    member_code      VARCHAR(20)   NOT NULL,
    sd_principal     DECIMAL(12,2) NOT NULL,
    sd_interest      DECIMAL(12,2) NOT NULL DEFAULT 0,
    total_paid       DECIMAL(12,2) NOT NULL,
    int_rate         DECIMAL(5,2)  NOT NULL DEFAULT 0,
    withdrawal_date  DATE          NOT NULL,
    createdby        INT           NOT NULL,
    createddate      DATETIME      NOT NULL DEFAULT GETDATE(),
    remarks          VARCHAR(200)
);
"""


# ════════════════════════════════════════════════════════════
#  NAV MENU: Add to base.html sidebar / navigation
# ════════════════════════════════════════════════════════════
"""
<a href="{{ url_for('sd_withdraw.sd_withdraw') }}" class="nav-link">
    <i class="bi bi-shield-check me-2"></i>Security Deposit Withdrawal
</a>
"""
