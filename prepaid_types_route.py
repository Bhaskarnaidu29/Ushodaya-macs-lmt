# ============ PREPAID TYPES (UPDATED) ============
@settings_bp.route('/prepaid-types', methods=['GET', 'POST'])
def prepaid_types():
    """Manage prepaid loan closure types with full configuration."""
    conn = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        if not check_table_exists(cursor, 'PrepaidType'):
            flash('⚠️ PrepaidType table does not exist', 'warning')
            return render_template('settings_prepaid_types.html', prepaid_types=[])
        
        if request.method == 'POST':
            action = request.form.get('action')
            
            if action == 'add':
                # Get form values
                prepaidtypename = request.form.get('prepaidtypename')
                active = 1 if request.form.get('active') else 0
                haspreclosurecharges = 1 if request.form.get('haspreclosurecharges') else 0
                preclosurechargespercent = float(request.form.get('preclosurechargespercent', 0) or 0)
                fullinterest = 1 if request.form.get('fullinterest') else 0
                fullsavings = 1 if request.form.get('fullsavings') else 0
                
                cursor.execute("""
                    INSERT INTO PrepaidType (
                        prepaidtypename, 
                        active, 
                        haspreclosurecharges,
                        preclosurechargespercent,
                        fullinterest,
                        fullsavings
                    ) VALUES (?, ?, ?, ?, ?, ?)
                """, (prepaidtypename, active, haspreclosurecharges, 
                      preclosurechargespercent, fullinterest, fullsavings))
                
                conn.commit()
                flash(f'✅ Prepaid type "{prepaidtypename}" added successfully!', 'success')
                
            elif action == 'update':
                # Get form values
                prepaidtypeid = request.form.get('prepaidtypeid')
                prepaidtypename = request.form.get('prepaidtypename')
                active = 1 if request.form.get('active') else 0
                haspreclosurecharges = 1 if request.form.get('haspreclosurecharges') else 0
                preclosurechargespercent = float(request.form.get('preclosurechargespercent', 0) or 0)
                fullinterest = 1 if request.form.get('fullinterest') else 0
                fullsavings = 1 if request.form.get('fullsavings') else 0
                
                cursor.execute("""
                    UPDATE PrepaidType 
                    SET prepaidtypename = ?,
                        active = ?,
                        haspreclosurecharges = ?,
                        preclosurechargespercent = ?,
                        fullinterest = ?,
                        fullsavings = ?
                    WHERE prepaidtypeid = ?
                """, (prepaidtypename, active, haspreclosurecharges, 
                      preclosurechargespercent, fullinterest, fullsavings, prepaidtypeid))
                
                conn.commit()
                flash(f'✅ Prepaid type "{prepaidtypename}" updated successfully!', 'success')
                
            return redirect(url_for('settings_bp.prepaid_types'))
        
        # Fetch all prepaid types
        cursor.execute("""
            SELECT 
                prepaidtypeid,                              -- [0]
                prepaidtypename,                            -- [1]
                ISNULL(active, 0),                          -- [2]
                ISNULL(haspreclosurecharges, 0),            -- [3]
                ISNULL(preclosurechargespercent, 0),        -- [4]
                ISNULL(fullinterest, 0),                    -- [5]
                ISNULL(fullsavings, 0)                      -- [6]
            FROM PrepaidType 
            ORDER BY prepaidtypename
        """)
        prepaid_types = cursor.fetchall()
        
        return render_template('settings_prepaid_types.html', prepaid_types=prepaid_types)
        
    except Exception as e:
        flash(f'Error: {str(e)}', 'danger')
        import traceback
        traceback.print_exc()
        return render_template('settings_prepaid_types.html', prepaid_types=[])
    finally:
        if conn:
            conn.close()
