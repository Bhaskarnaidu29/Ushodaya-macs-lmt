from flask import Blueprint, render_template, request, redirect, url_for, flash
import pyodbc

product_bp = Blueprint("product", __name__, template_folder="templates")

# --- DB Connection Helper ---
from db import get_db_connection   # âœ… Reuse main app DB connection


# --- Product List ---
@product_bp.route("/", methods=["GET"])
def product_list():
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM Product")
    rows = cursor.fetchall()
    conn.close()

    products = []
    for row in rows:
        products.append({
            "ProductID": row.ProductID,
            "Name": row.Name,
            "Active": row.Active,
            "MethodType": row.MethodType,
            "InterestType": row.InterestType,
            "Interest": row.Interest,
            "PaymentType": row.PaymentType,
            "Tenure": row.Tenure,
            "FixedTenure": row.FixedTenure,
            "ProcessingFee": row.ProcessingFee,
            "ProcessingFeeType": row.ProcessingFeeType,
            "ProcessingFeeValue": row.ProcessingFeeValue,
            "Savings": row.Savings,
            "AdditionalSavings": row.AdditionalSavings,
            "SavingsType": row.SavingsType,
            "SavingsValue": row.SavingsValue,
            "MemberInsurance": row.MemberInsurance,
            "MemberInsuranceType": row.MemberInsuranceType,
            "MemberInsuranceValue": row.MemberInsuranceValue,
            "MemberInsuranceAgeLimit": row.MemberInsuranceAgeLimit,
            "NomineeInsurance": row.NomineeInsurance,
            "NomineeInsuranceType": row.NomineeInsuranceType,
            "NomineeInsuranceValue": row.NomineeInsuranceValue,
            "NomineeInsuranceAgeLimit": row.NomineeInsuranceAgeLimit,
            "SecurityDeposit": row.SecurityDeposit,
            "SecurityDepositPercent": row.SecurityDepositPercent,
            "SecurityDepositWithdraw": row.SecurityDepositWithdraw,
            "Notes": row.Notes,
            "CreatedAt": row.CreatedAt
        })

    return render_template("product.html", products=products)


# --- Add Product ---
@product_bp.route("/add", methods=["POST"])
def product_add():
    data = request.form

    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute("""
        INSERT INTO Product (
            Name, Active, MethodType, InterestType, Interest, PaymentType, Tenure, FixedTenure,
            ProcessingFee, ProcessingFeeType, ProcessingFeeValue,
            Savings, AdditionalSavings, SavingsType, SavingsValue,
            MemberInsurance, MemberInsuranceType, MemberInsuranceValue, MemberInsuranceAgeLimit,
            NomineeInsurance, NomineeInsuranceType, NomineeInsuranceValue, NomineeInsuranceAgeLimit,
            SecurityDeposit, SecurityDepositPercent, SecurityDepositWithdraw, Notes
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        data.get("Name"),
        data.get("Active", 0),
        data.get("MethodType"),
        data.get("InterestType"),
        data.get("Interest"),
        data.get("PaymentType"),
        data.get("Tenure"),
        data.get("FixedTenure", 0),
        data.get("ProcessingFee", 0),
        data.get("ProcessingFeeType"),
        data.get("ProcessingFeeValue"),
        data.get("Savings", 0),
        data.get("AdditionalSavings", 0),
        data.get("SavingsType"),
        data.get("SavingsValue"),
        data.get("MemberInsurance", 0),
        data.get("MemberInsuranceType"),
        data.get("MemberInsuranceValue"),
        data.get("MemberInsuranceAgeLimit"),
        data.get("NomineeInsurance", 0),
        data.get("NomineeInsuranceType"),
        data.get("NomineeInsuranceValue"),
        data.get("NomineeInsuranceAgeLimit"),
        data.get("SecurityDeposit", 0),
        data.get("SecurityDepositPercent"),
        data.get("SecurityDepositWithdraw"),
        data.get("Notes")
    ))

    conn.commit()
    conn.close()

    flash("Product added successfully!", "success")
    return redirect(url_for("product.product_list"))
