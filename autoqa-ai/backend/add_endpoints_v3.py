with open(r'app.py', 'r') as f:
    content = f.read()

# Find the exact position to insert
target = 'return jsonify({"success": True, "events": events})'
idx = content.find(target)

if idx == -1:
    print("ERROR: Could not find target string")
    exit(1)

# Find the next function definition after api_security_audit_list
next_func = content.find('def review_autonomous_run', content.find('def api_security_audit_list'))
print(f"Found return at index: {idx}")
print(f"Next function at index: {next_func}")

if idx == -1 or next_func == -1:
    print("ERROR: Could not find insertion points")
    exit(1)

# Our new endpoint code
insert_text = '''

# ---- Phase 5D: Finding Lifecycle Management Endpoints ----

@app.route("/api/security/findings", methods=["GET"])
@jwt_required()
def api_security_findings_list():
    """List findings for the current user with filtering options."""
    from agentqe.security.finding_lifecycle import get_lifecycle_manager
    
    user_id = int(get_jwt_identity())
    lifecycle_state = request.args.get("lifecycle_state")
    verification_state = request.args.get("verification_state")
    severity = request.args.get("severity")
    validator_id = request.args.get("validator_id")
    run_id = request.args.get("run_id", type=int)
    limit = min(int(request.args.get("limit", 50)), 100)
    offset = int(request.args.get("offset", 0))
    
    # Build query
    conditions = ["f.run_id = ar.id", "ar.user_id = ?", "ar.run_type = 'security'"]
    params = [int(get_jwt_identity())]
    
    if lifecycle_state:
        conditions.append("f.lifecycle_state = ?")
        params.append(lifecycle_state)
    if verification_state:
        conditions.append("f.verification_state = ?")
        params.append(verification_state)
    if severity:
        conditions.append("f.severity = ?")
        params.append(severity)
    if validator_id:
        conditions.append("f.validator_id = ?")
        params.append(validator_id)
    if run_id:
        conditions.append("f.run_id = ?")
        params.append(run_id)
    
    where_clause = " AND ".join(conditions)
    query = f"""
        SELECT f.*, l.lifecycle_state, l.verification_state, l.resolution_type,
               l.resolution_reason, l.resolved_at, l.resolved_by,
               l.acknowledged_at, l.acknowledged_by, l.remediation_started_at,
               l.remediation_started_by, l.resolved_at, l.resolved_by,
               l.accepted_risk_at, l.accepted_risk_by, l.risk_acceptance_reason,
               l.reopened_count, l.verification_state, l.verification_confidence,
               l.version
        FROM security_findings f
        LEFT JOIN security_finding_lifecycle l ON f.id = l.finding_id
        JOIN autonomous_runs ar ON f.run_id = ar.id
        WHERE {where_clause}
        ORDER BY f.created_at DESC
        LIMIT ? OFFSET ?
    """
    params.extend([limit, offset])
    
    findings = execute_query(query, tuple(params), fetch=True)
    return jsonify({"success": True, "findings": findings})


@app.route("/api/security/findings/<int:finding_id>", methods=["GET"])
@jwt_required()
def api_security_finding_detail(finding_id):
    """Get detailed finding with lifecycle information."""
    from agentqe.security.finding_lifecycle import get_lifecycle_manager
    
    user_id = int(get_jwt_identity())
    lifecycle_mgr = get_lifecycle_manager()
    finding = lifecycle_mgr.get_finding_with_lifecycle(finding_id, int(get_jwt_identity()))
    
    if not finding:
        return jsonify({"error": "Finding not found"}), 404
    
    return jsonify({"success": True, "finding": finding})


@app.route("/api/security/findings/<int:finding_id>/history", methods=["GET"])
@jwt_required()
def api_security_finding_history(finding_id):
    """Get lifecycle history for a finding."""
    from agentqe.security.finding_lifecycle import get_lifecycle_manager
    
    lifecycle_mgr = get_lifecycle_manager()
    
    # Verify ownership
    rows = execute_query(
        """SELECT f.id FROM security_findings f
           JOIN autonomous_runs ar ON f.run_id = ar.id
           WHERE f.id = ? AND ar.user_id = ? AND ar.run_type = 'security'""",
        (finding_id, int(get_jwt_identity())), fetch=True)
    if not rows:
        return jsonify({"error": "Finding not found"}), 404
    
    history = get_lifecycle_manager().get_history(finding_id)
    return jsonify({"success": True, "history": history})


@app.route("/api/security/findings/<int:finding_id>/transition", methods=["POST"])
@jwt_required()
def api_security_finding_transition(finding_id):
    """Transition finding to a new lifecycle state."""
    from agentqe.security.finding_lifecycle import get_lifecycle_manager, LifecycleState, ResolutionType
    
    user_id = int(get_jwt_identity())
    data = request.get_json() or {}
    
    lifecycle_mgr = get_lifecycle_manager()
    
    # Validate input
    new_state_str = data.get("lifecycle_state")
    if not new_state_str:
        return jsonify({"error": "lifecycle_state is required"}), 400
    
    try:
        new_state = LifecycleState(new_state_str)
    except ValueError:
        return jsonify({"error": f"Invalid lifecycle state: {new_state_str}"}), 400
    
    reason = data.get("reason", "").strip()
    if not reason:
        return jsonify({"error": "Reason is required"}), 400
    
    evidence_refs = data.get("evidence_refs", [])
    resolution_type = data.get("resolution_type")
    resolution_reason = data.get("resolution_reason", "")
    resolution_evidence_refs = data.get("resolution_evidence_refs", [])
    expected_version = data.get("expected_version")
    
    # Validate resolution requirements
    if new_state == LifecycleState.RESOLVED and not resolution_type:
        return jsonify({"error": "Resolution type required when resolving"}), 400
    
    # Convert enums
    try:
        if resolution_type:
            resolution_type = ResolutionType(resolution_type)
    except ValueError:
        return jsonify({"error": f"Invalid resolution type: {resolution_type}"}), 400
    
    try:
        new_state = LifecycleState(new_state_str)
    except ValueError:
        return jsonify({"error": f"Invalid lifecycle state: {new_state_str}"}), 400
    
    # Get lifecycle manager
    from agentqe.security.finding_lifecycle import get_lifecycle_manager
    lifecycle_mgr = get_lifecycle_manager()
    
    # Perform transition
    if new_state == LifecycleState.ACKNOWLEDGED:
        success, msg = lifecycle_mgr.acknowledge_finding(
            finding_id, int(get_jwt_identity()), evidence_refs=evidence_refs
        )
    elif new_state == LifecycleState.IN_REMEDIATION:
        success, msg = lifecycle_mgr.start_remediation(
            finding_id, int(get_jwt_identity()), evidence_refs=evidence_refs
        )
    elif new_state == LifecycleState.RESOLVED:
        if not resolution_type:
            return jsonify({"error": "Resolution type required"}), 400
        success, msg = lifecycle_mgr.resolve_finding(
            finding_id, int(get_jwt_identity()), 
            resolution_type=ResolutionType(resolution_type),
            resolution_reason=resolution_reason,
            resolution_evidence_refs=resolution_evidence_refs,
            expected_version=data.get("expected_version")
        )
    elif new_state == LifecycleState.ACCEPTED_RISK:
        success, msg = lifecycle_mgr.accept_risk(
            finding_id, int(get_jwt_identity()), reason=resolution_reason
        )
    elif new_state == LifecycleState.REOPENED:
        success, msg = lifecycle_mgr.reopen_finding(
            finding_id, int(get_jwt_identity()), 
            recurrence_evidence=data.get("recurrence_evidence", [])
        )
    elif new_state == LifecycleState.ACKNOWLEDGED:
        success, msg = lifecycle_mgr.acknowledge_finding(
            finding_id, int(get_jwt_identity()), evidence_refs=evidence_refs
        )
    else:
        return jsonify({"error": f"Transition to {new_state.value} not supported via this endpoint"}), 400
    
    if not success:
        return jsonify({"error": msg}), 400
    
    return jsonify({"success": True, "message": msg})


@app.route("/api/security/findings/<int:finding_id>/reverify", methods=["POST"])
@jwt_required()
def api_security_finding_reverify(finding_id):
    """Request reverification of a finding."""
    from agentqe.security.finding_lifecycle import get_lifecycle_manager
    from agentqe.security.finding_verifier import VerificationState
    
    user_id = int(get_jwt_identity())
    data = request.get_json() or {}
    
    lifecycle_mgr = get_lifecycle_manager()
    
    new_verification_state = data.get("verification_state", "verified")
    verification_confidence = data.get("verification_confidence", 0.7)
    
    try:
        new_state = VerificationState(new_verification_state)
    except ValueError:
        return jsonify({"error": f"Invalid verification state: {new_verification_state}"}), 400
    
    verification_confidence = float(verification_confidence)
    if not 0 <= verification_confidence <= 1:
        return jsonify({"error": "verification_confidence must be between 0 and 1"}), 400
    
    success, msg = lifecycle_mgr.request_reverification(
        finding_id, int(get_jwt_identity()), 
        new_verification_state=new_state,
        verification_confidence=verification_confidence
    )
    
    if not success:
        return jsonify({"error": msg}), 400
    
    return jsonify({"success": True, "message": msg})


# ---- End Phase 5D: Finding Lifecycle Endpoints ----

# Insert the new code
insert_pos = content.find('return jsonify({"success": True, "events": events})') + len('return jsonify({"success": True, "events": events})')
next_func = content.find('def review_autonomous_run', content.find('def api_security_audit_list'))

new_content = content[:insert_pos] + '\n\n# ---- Phase 5D: Finding Lifecycle Management Endpoints ----\n\n' + insert_text + '\n\n# ---- End Phase 5D: Finding Lifecycle Endpoints ----\n\n' + content[next_func:]

with open('app.py', 'w') as f:
    f.write(new_content)

print("Done - endpoints added successfully!")