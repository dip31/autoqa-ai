with open('app.py', 'r') as f:
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

# Read the insert text from file
with open('insert_code.txt', 'r', encoding='utf-8') as f:
    insert_text = f.read()

insert_pos = content.find('return jsonify({"success": True, "events": events})') + len('return jsonify({"success": True, "events": events})')
next_func = content.find('def review_autonomous_run', content.find('def api_security_audit_list'))

new_content = content[:insert_pos] + '\n\n# ---- Phase 5D: Finding Lifecycle Management Endpoints ----\n\n' + insert_text + '\n\n# ---- End Phase 5D: Finding Lifecycle Endpoints ----\n\n' + content[next_func:]

with open('app.py', 'w') as f:
    f.write(new_content)

print("Done - endpoints added successfully!")