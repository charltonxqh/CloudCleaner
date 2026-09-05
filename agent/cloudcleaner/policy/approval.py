"""Strict approval command parsing. Case-sensitive exact match, no y/n."""


def parse_approval(raw: str, expected_resource_id: str) -> dict:
    expected = f"APPROVE {expected_resource_id}"

    if raw != raw.strip():
        return {"valid": False, "error": "leading or trailing whitespace", "expected": expected}
    if not raw.startswith("APPROVE "):
        return {"valid": False, "error": "must start with 'APPROVE '", "expected": expected}

    resource_id = raw[len("APPROVE "):]
    if not resource_id:
        return {"valid": False, "error": "missing resource id", "expected": expected}
    if resource_id != expected_resource_id:
        return {"valid": False, "error": f"expected {expected_resource_id}", "expected": expected}

    return {"valid": True, "resource_id": resource_id}


class ApprovalGate:
    def __init__(self, max_attempts: int = 3):
        self.max_attempts = max_attempts
        self.attempts = 0
        self.locked = False

    def attempt(self, raw: str, expected_resource_id: str) -> dict:
        if self.locked:
            return {"valid": False, "error": "gate locked after too many failed attempts"}

        result = parse_approval(raw, expected_resource_id)
        if not result["valid"]:
            self.attempts += 1
            if self.attempts >= self.max_attempts:
                self.locked = True
                result["error"] += " (gate now locked)"
            result["attempts_remaining"] = max(0, self.max_attempts - self.attempts)
        return result
