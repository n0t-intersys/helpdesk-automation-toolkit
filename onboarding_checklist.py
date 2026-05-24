#!/usr/bin/env python3
"""
Onboarding Checklist Generator — Produces role-based onboarding task lists
with mock Active Directory provisioning steps.

Roles supported: new_hire, contractor, admin, executive, vendor

Usage:
    python onboarding_checklist.py --role new_hire --name "Jane Doe" --dept Engineering
    python onboarding_checklist.py --role contractor --name "Bob Smith" --dept Finance --output checklist.md
    python onboarding_checklist.py --role admin --name "Alice Chen" --dept IT --start-date 2025-02-01
"""

import argparse
import json
import logging
import sys
from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path
from typing import Optional

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Task catalog
# ---------------------------------------------------------------------------

COMMON_TASKS: list[dict] = [
    {"id": "HR-001", "category": "HR", "task": "Complete I-9 employment eligibility verification", "owner": "HR", "day": 0},
    {"id": "HR-002", "category": "HR", "task": "Sign NDA and acceptable use policy", "owner": "HR", "day": 0},
    {"id": "HR-003", "category": "HR", "task": "Enroll in benefits (health, dental, 401k)", "owner": "HR", "day": 5},
    {"id": "IT-001", "category": "IT", "task": "Create Active Directory user account", "owner": "IT", "day": -2},
    {"id": "IT-002", "category": "IT", "task": "Assign user to base security groups (Domain Users, VPN-Users)", "owner": "IT", "day": -2},
    {"id": "IT-003", "category": "IT", "task": "Provision Microsoft 365 license and mailbox", "owner": "IT", "day": -2},
    {"id": "IT-004", "category": "IT", "task": "Configure MFA (Microsoft Authenticator app)", "owner": "IT/User", "day": 0},
    {"id": "IT-005", "category": "IT", "task": "Deliver and image workstation (OS + standard software)", "owner": "IT", "day": -1},
    {"id": "IT-006", "category": "IT", "task": "Install endpoint protection (CrowdStrike Falcon)", "owner": "IT", "day": -1},
    {"id": "IT-007", "category": "IT", "task": "Enroll device in MDM (Intune)", "owner": "IT", "day": 0},
    {"id": "IT-008", "category": "IT", "task": "Configure VPN client and test connectivity", "owner": "IT", "day": 0},
    {"id": "SEC-001", "category": "Security", "task": "Complete mandatory security awareness training", "owner": "User", "day": 1},
    {"id": "SEC-002", "category": "Security", "task": "Review and acknowledge information security policy", "owner": "User", "day": 1},
    {"id": "MGR-001", "category": "Manager", "task": "Assign 30/60/90 day goals", "owner": "Manager", "day": 0},
    {"id": "MGR-002", "category": "Manager", "task": "Schedule first 1:1 meeting", "owner": "Manager", "day": 0},
]

ROLE_SPECIFIC_TASKS: dict[str, list[dict]] = {
    "new_hire": [
        {"id": "NH-001", "category": "IT", "task": "Grant access to department SharePoint and Teams channels", "owner": "IT", "day": 0},
        {"id": "NH-002", "category": "IT", "task": "Add to department distribution list", "owner": "IT", "day": 0},
        {"id": "NH-003", "category": "Manager", "task": "Assign onboarding buddy", "owner": "Manager", "day": 0},
        {"id": "NH-004", "category": "HR", "task": "Schedule office tour and badge photo", "owner": "HR", "day": 0},
        {"id": "NH-005", "category": "IT", "task": "Install department-specific applications", "owner": "IT", "day": 1},
    ],
    "contractor": [
        {"id": "CTR-001", "category": "Security", "task": "Complete third-party access agreement", "owner": "Legal/HR", "day": -1},
        {"id": "CTR-002", "category": "IT", "task": "Create contractor AD account (suffix: .contractor)", "owner": "IT", "day": -1},
        {"id": "CTR-003", "category": "IT", "task": "Apply contractor OU restrictions (no local admin, internet filter)", "owner": "IT", "day": -1},
        {"id": "CTR-004", "category": "Security", "task": "Define data access scope — limit to project resources only", "owner": "Security", "day": 0},
        {"id": "CTR-005", "category": "IT", "task": "Set account expiry to contract end date", "owner": "IT", "day": -1},
        {"id": "CTR-006", "category": "IT", "task": "Issue temporary badge (contractor designation)", "owner": "Facilities", "day": 0},
        {"id": "CTR-007", "category": "Security", "task": "Enable enhanced audit logging for contractor account", "owner": "Security", "day": 0},
    ],
    "admin": [
        {"id": "ADM-001", "category": "Security", "task": "Create dedicated admin account (admin.username convention)", "owner": "IT", "day": -2},
        {"id": "ADM-002", "category": "Security", "task": "Add to Domain Admins group (requires manager + CISO approval)", "owner": "Security", "day": -2},
        {"id": "ADM-003", "category": "IT", "task": "Configure PAW (Privileged Access Workstation)", "owner": "IT", "day": -1},
        {"id": "ADM-004", "category": "Security", "task": "Enable privileged session recording in CyberArk/PAM", "owner": "Security", "day": 0},
        {"id": "ADM-005", "category": "Security", "task": "Enroll admin account in Just-In-Time access workflow", "owner": "Security", "day": 0},
        {"id": "ADM-006", "category": "Security", "task": "Complete Privileged Access training module", "owner": "User", "day": 1},
        {"id": "ADM-007", "category": "IT", "task": "Grant access to ITSM admin console (ServiceNow)", "owner": "IT", "day": 0},
        {"id": "ADM-008", "category": "Security", "task": "Brief on incident response escalation path", "owner": "Security", "day": 1},
    ],
    "executive": [
        {"id": "EXC-001", "category": "IT", "task": "Provision executive M365 E5 license (e-discovery enabled)", "owner": "IT", "day": -2},
        {"id": "EXC-002", "category": "Security", "task": "Enable executive email threat protection (Defender for Office 365 P2)", "owner": "Security", "day": -2},
        {"id": "EXC-003", "category": "IT", "task": "Assign dedicated IT support contact", "owner": "IT", "day": 0},
        {"id": "EXC-004", "category": "Security", "task": "Brief on targeted attack awareness (spear phishing, vishing)", "owner": "Security", "day": 1},
        {"id": "EXC-005", "category": "IT", "task": "Configure mobile device (iPhone/Android) with Intune MAM", "owner": "IT", "day": 0},
    ],
    "vendor": [
        {"id": "VND-001", "category": "Security", "task": "Complete vendor security questionnaire (VSQ)", "owner": "Vendor/Security", "day": -5},
        {"id": "VND-002", "category": "Legal", "task": "Execute DPA/BAA if applicable (GDPR/HIPAA)", "owner": "Legal", "day": -5},
        {"id": "VND-003", "category": "IT", "task": "Create vendor-specific service account (least-privilege)", "owner": "IT", "day": -1},
        {"id": "VND-004", "category": "Security", "task": "Configure IP allowlisting for vendor access", "owner": "Security", "day": 0},
        {"id": "VND-005", "category": "Security", "task": "Define SLA for vendor response to security incidents", "owner": "Security", "day": 0},
    ],
}

AD_MOCK_COMMANDS: dict[str, list[str]] = {
    "create_user": [
        "# Create AD user account",
        'New-ADUser -Name "{display_name}" -SamAccountName "{username}" \\',
        '    -UserPrincipalName "{username}@company.com" \\',
        '    -GivenName "{first_name}" -Surname "{last_name}" \\',
        '    -Department "{dept}" -Title "{role}" \\',
        '    -AccountPassword (ConvertTo-SecureString "TempPass@{year}!" -AsPlainText -Force) \\',
        "    -PasswordNeverExpires $false -ChangePasswordAtLogon $true -Enabled $true",
        "",
        "# Set OU placement",
        'Move-ADObject -Identity (Get-ADUser "{username}").DistinguishedName \\',
        '    -TargetPath "OU={dept},OU=Users,DC=company,DC=com"',
    ],
    "assign_groups": [
        "# Assign to standard groups",
        'Add-ADGroupMember -Identity "Domain Users" -Members "{username}"',
        'Add-ADGroupMember -Identity "VPN-Users" -Members "{username}"',
        'Add-ADGroupMember -Identity "M365-Licensed" -Members "{username}"',
        'Add-ADGroupMember -Identity "Dept-{dept}" -Members "{username}"',
    ],
    "contractor_restrictions": [
        "# Apply contractor OU and restrictions",
        'Move-ADObject -Identity (Get-ADUser "{username}").DistinguishedName \\',
        '    -TargetPath "OU=Contractors,OU=Users,DC=company,DC=com"',
        "",
        "# Set account expiry",
        'Set-ADAccountExpiration -Identity "{username}" -DateTime "{expiry_date}"',
        "",
        "# Deny local logon via GPO — apply ContractorBaseline GPO",
        'New-GPLink -Name "ContractorBaseline" -Target "OU=Contractors,OU=Users,DC=company,DC=com"',
    ],
    "admin_account": [
        "# Create privileged admin account",
        'New-ADUser -Name "admin.{username}" -SamAccountName "admin.{username}" \\',
        '    -UserPrincipalName "admin.{username}@company.com" \\',
        '    -Description "Privileged admin account for {display_name}" \\',
        "    -Enabled $true -PasswordNeverExpires $false",
        "",
        "# Add to privileged groups (requires change approval)",
        'Add-ADGroupMember -Identity "Server Operators" -Members "admin.{username}"',
        "# Domain Admins addition requires dual approval — see change process",
    ],
}


# ---------------------------------------------------------------------------
# Checklist builder
# ---------------------------------------------------------------------------

@dataclass
class OnboardingChecklist:
    name: str
    role: str
    department: str
    start_date: date
    username: str = field(init=False)
    tasks: list[dict] = field(default_factory=list)

    def __post_init__(self) -> None:
        parts = self.name.lower().split()
        self.username = f"{parts[0][0]}.{parts[-1]}" if len(parts) >= 2 else parts[0]

    def build(self) -> None:
        all_tasks = COMMON_TASKS + ROLE_SPECIFIC_TASKS.get(self.role, [])
        self.tasks = sorted(all_tasks, key=lambda t: (t["day"], t["id"]))

    def _due_date(self, day_offset: int) -> str:
        from datetime import timedelta
        d = self.start_date + timedelta(days=day_offset)
        prefix = "Pre-start" if day_offset < 0 else f"Day +{day_offset}" if day_offset > 0 else "Day 0 (Start)"
        return f"{prefix} ({d.strftime('%Y-%m-%d')})"

    def _render_ad_commands(self) -> str:
        subs = {
            "display_name": self.name,
            "username": self.username,
            "first_name": self.name.split()[0],
            "last_name": self.name.split()[-1],
            "dept": self.department,
            "role": self.role.replace("_", " ").title(),
            "year": str(self.start_date.year),
            "expiry_date": "2025-12-31",
        }
        sections = ["create_user", "assign_groups"]
        if self.role == "contractor":
            sections.append("contractor_restrictions")
        if self.role == "admin":
            sections.append("admin_account")

        lines = ["```powershell"]
        for section in sections:
            for line in AD_MOCK_COMMANDS[section]:
                formatted = line
                for k, v in subs.items():
                    formatted = formatted.replace(f"{{{k}}}", v)
                lines.append(formatted)
            lines.append("")
        lines.append("```")
        return "\n".join(lines)

    def to_markdown(self) -> str:
        lines = [
            f"# Onboarding Checklist: {self.name}",
            f"",
            f"| Field | Value |",
            f"|-------|-------|",
            f"| **Name** | {self.name} |",
            f"| **Role Type** | {self.role.replace('_', ' ').title()} |",
            f"| **Department** | {self.department} |",
            f"| **Username** | {self.username}@company.com |",
            f"| **Start Date** | {self.start_date.strftime('%B %d, %Y')} |",
            f"| **Generated** | {datetime.now().strftime('%Y-%m-%d %H:%M')} |",
            f"",
            f"---",
            f"",
            f"## Task List",
            f"",
        ]

        current_day = None
        for task in self.tasks:
            if task["day"] != current_day:
                current_day = task["day"]
                lines.append(f"### {self._due_date(current_day)}")
                lines.append("")

            status = "[ ]"
            lines.append(
                f"- {status} **[{task['id']}]** `{task['category']}` — "
                f"{task['task']} *(Owner: {task['owner']})*"
            )
        lines.append("")
        lines.append("---")
        lines.append("")
        lines.append("## Active Directory Provisioning Commands")
        lines.append("")
        lines.append("> ⚠️ Run these commands from a Domain Controller with appropriate privileges.")
        lines.append("")
        lines.append(self._render_ad_commands())
        lines.append("")
        lines.append("---")
        lines.append(f"*Generated by onboarding_checklist.py — IT Service Desk Automation Suite*")
        return "\n".join(lines)

    def to_json(self) -> dict:
        return {
            "name": self.name,
            "role": self.role,
            "department": self.department,
            "username": self.username,
            "start_date": self.start_date.isoformat(),
            "task_count": len(self.tasks),
            "tasks": self.tasks,
        }


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Generate role-based IT onboarding checklists.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument("--name", required=True, help='Full name, e.g. "Jane Doe"')
    parser.add_argument(
        "--role",
        required=True,
        choices=list(ROLE_SPECIFIC_TASKS.keys()) + ["new_hire"],
        help="User role type",
    )
    parser.add_argument("--dept", default="General", help="Department name")
    parser.add_argument("--start-date", default=None, help="Start date YYYY-MM-DD (default: today)")
    parser.add_argument("--output", type=Path, help="Write checklist to file (.md or .json)")
    parser.add_argument("--format", choices=["markdown", "json"], default="markdown")
    return parser.parse_args()


def main() -> int:
    args = parse_args()

    start = (
        date.fromisoformat(args.start_date)
        if args.start_date
        else date.today()
    )

    checklist = OnboardingChecklist(
        name=args.name,
        role=args.role,
        department=args.dept,
        start_date=start,
    )
    checklist.build()

    logger.info(
        "Generated %d tasks for %s (%s) starting %s",
        len(checklist.tasks),
        args.name,
        args.role,
        start.isoformat(),
    )

    if args.format == "json":
        content = json.dumps(checklist.to_json(), indent=2)
    else:
        content = checklist.to_markdown()

    if args.output:
        args.output.write_text(content)
        logger.info("Checklist written to %s", args.output)
    else:
        print(content)

    return 0


if __name__ == "__main__":
    sys.exit(main())
