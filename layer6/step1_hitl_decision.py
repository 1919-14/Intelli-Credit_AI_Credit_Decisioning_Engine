import json
from datetime import datetime

def process_layer6_decision(db_conn, app_id, user_id, user_role, user_name, has_large_loan_perm, action, reason, category):
    """
    Evaluates the Layer 6 decision (Accept/Override).
    Handles Maker-Checker routing if the limit > 200 Lakhs.
    Submits to Layer 7 if approved, or puts into PENDING_CHECKER state.

    Returns: tuple(status_code, response_dict)
    """
    cur = db_conn.cursor(dictionary=True)
    cur.execute("SELECT * FROM applications WHERE id=%s", (app_id,))
    app_data = cur.fetchone()

    if not app_data:
        cur.close()
        return 404, {"error": "Application not found"}

    current_status = app_data.get('status', '')
    
    # Validation
    if action == "OVERRIDE" and len(reason.strip()) < 50:
        cur.close()
        return 400, {"error": "Override reason must be at least 50 characters."}

    # Extract limit_lakhs from Layer 5 Output
    limit_lakhs = 0
    l5_output = app_data.get('layer5_output')
    if l5_output:
        try:
            l5 = json.loads(l5_output) if isinstance(l5_output, str) else l5_output
            decision_summary = l5.get('decision_summary', {})
            limit_lakhs = decision_summary.get('sanction_amount_lakhs', 0)
        except Exception:
            pass

    is_checker_approval = False
    needs_checker = limit_lakhs > 200
    
    if needs_checker:
        if current_status == "PENDING_CHECKER":
            if not has_large_loan_perm:
                cur.close()
                return 403, {"error": "You do not have the 'APPROVE_LARGE_LOAN' permission required to approve this >₹200L loan."}
            is_checker_approval = True
        else:
            if not has_large_loan_perm:
                _update_to_pending_checker(cur, app_id)
                _log_audit(cur, user_id, 'L6_MAKER_SUBMIT', app_data['case_id'], {
                    "action": action, "category": category, "reason": reason, "routed_to": "CHECKER", "limit_lakhs": limit_lakhs
                })
                db_conn.commit()
                cur.close()
                return 200, {"status": "pending_checker", "message": f"Loan (₹{limit_lakhs}L) exceeds ₹200L limit. Routed to Senior Credit Manager for Checker approval."}
            else:
                is_checker_approval = True  # They had permission right away, so it counts as checker auth

    new_status = "approved" if action == "ACCEPT" else "overridden"
    
    decision_payload = {
        "final_action": action,
        "reason": reason,
        "category": category,
        "approved_by_id": user_id,
        "approved_by_name": user_name,
        "timestamp": datetime.utcnow().isoformat(),
        "is_checker_approval": is_checker_approval,
        "limit_lakhs": limit_lakhs
    }

    cur.execute("UPDATE applications SET status=%s, current_layer=6, completed_at=NOW() WHERE id=%s", (new_status, app_id))

    _log_audit(cur, user_id, 'L6_FINAL_APPROVAL' if not is_checker_approval else 'L6_CHECKER_APPROVAL', 
              app_data['case_id'], decision_payload)
              
    db_conn.commit()
    cur.close()
    
    return 200, {"status": new_status, "message": "Decision finalized and digitally logged."}

def _update_to_pending_checker(cur, app_id):
    cur.execute("UPDATE applications SET status='PENDING_CHECKER' WHERE id=%s", (app_id,))

def _log_audit(cur, actor_id, action, target, details):
    cur.execute("INSERT INTO audit_logs (actor_id, action, target, details) VALUES (%s,%s,%s,%s)",
                (actor_id, action, target, json.dumps(details)))
