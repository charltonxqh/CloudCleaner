"""Shared plan rendering, used by the CLI and mirrored by the UI."""


def render_plan(payload: dict) -> str:
    r, rec, plan = payload["resource"], payload["recommendation"], payload["plan"]

    lines = [
        "",
        f"  {r['id']}  {r['name'] or '-'}  ({r['state']})  ${r['monthly_cost']}/mo",
    ]
    if r["billing_while_stopped"]:
        lines.append("  ** stopped, and still billing: storage and public IPv4 do not stop **")

    lines += [
        f"  verdict: {rec['action']} ({rec['confidence']:.0%}, {rec['severity']}) - {rec['reason']}",
        "",
        "  Teardown plan:",
    ]
    for s in plan["steps"]:
        mark = " " if s["reversible"] else "!"
        saving = f"${s['monthly_saving']:>6.2f}" if s["monthly_saving"] else "       "
        lines.append(f"   {mark} {s['order']}. {s['action']:<21} {s['resource_id']:<20}"
                     f"{saving}  {s['reason']}")

    lines += [
        f"{'':>30}{'':<20}{'-' * 7}",
        f"{'':>30}{'':<20}${plan['total_monthly_saving']:>6.2f}/mo",
        "",
        f"  ! = irreversible ({plan['irreversible_count']} steps). Restore recipe saved.",
        "",
        f"  Type '{payload['expected_command']}' to run this plan, anything else to skip: ",
    ]
    return "\n".join(lines)
