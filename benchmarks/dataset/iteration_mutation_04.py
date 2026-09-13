"""Removes inactive sessions from the active_sessions dictionary in-place."""


def prune_inactive_sessions(sessions):
    for session_id in sessions:
        if not sessions[session_id].get("active"):
            del sessions[session_id]
    return sessions