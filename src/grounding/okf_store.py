"""Open Knowledge Format (OKF) curated policy catalog."""
from typing import Dict, List, Optional
from pydantic import BaseModel, Field


class PolicyDocument(BaseModel):
    """Structure for an OKF curated policy rule and handbook section."""
    section_id: str
    title: str
    category: str
    summary: str
    details: str
    entitlement_limits: Dict[str, str] = Field(default_factory=dict)
    citation_title: str
    citation_url: str
    tags: List[str] = Field(default_factory=list)


class OKFPolicyStore:
    """In-memory store of curated enterprise HR and IT policies aligned with OKF standards."""

    def __init__(self) -> None:
        self._policies: Dict[str, PolicyDocument] = {}
        self._load_baseline_policies()

    def _load_baseline_policies(self) -> None:
        """Initialize curated baseline policies from SDD."""
        
        # 1. Section 04.2: Bereavement Leave Policy (UC-1.1)
        self.add_policy(
            PolicyDocument(
                section_id="04.2",
                title="Bereavement Leave Policy",
                category="LEAVE",
                summary="Full-time employees are entitled to paid bereavement leave for immediate family members.",
                details="Under Section 04.2 (Bereavement Leave), full-time employees are entitled to up to 5 consecutive days of paid leave for immediate family members (spouse, child, parent, sibling) and up to 3 days for extended family members. No deduction is made from annual vacation balances.",
                entitlement_limits={
                    "immediate_family_days": "5 consecutive days",
                    "extended_family_days": "3 consecutive days",
                    "pay_status": "Fully Paid"
                },
                citation_title="View Policy Section 04.2",
                citation_url="https://hr.corp.internal/policies/04.2-bereavement",
                tags=["bereavement", "compassionate", "leave", "time off", "death", "family"]
            )
        )

        # 2. Section 08.3: Remote Work Hardware Allowance (UC-2.1)
        self.add_policy(
            PolicyDocument(
                section_id="08.3",
                title="Remote Work Hardware & Equipment Policy",
                category="EQUIPMENT",
                summary="Full-time remote workers are eligible for home office equipment procurement.",
                details="Under Section 08.3 (Remote Work Hardware Allowance), employees with approved 'REMOTE_FULL_TIME' status are entitled to order 1x 27-inch external monitor (up to $350 allowance), an ergonomic keyboard/mouse bundle, and a USB-C docking station via ServiceImmediately.",
                entitlement_limits={
                    "monitor_allowance": "$350 USD (1x 27-inch monitor)",
                    "accessories": "Keyboard, mouse, USB-C dock",
                    "eligibility": "REMOTE_FULL_TIME status in WorkWeek"
                },
                citation_title="View Policy Section 08.3",
                citation_url="https://hr.corp.internal/policies/08.3-remote-equipment",
                tags=["remote", "monitor", "hardware", "equipment", "allowance", "home office"]
            )
        )

        # 3. Section 19.2: Medical Leave & Outpatient Procedures (UC-2.2)
        self.add_policy(
            PolicyDocument(
                section_id="19.2",
                title="Medical Leave and Extended Absence Procedure",
                category="LEAVE",
                summary="Guidelines for taking short-term sick leave, outpatient procedures, and access routing.",
                details="Under Section 19.2 (Medical Leave & Extended Absence), outpatient medical leave is capped at 14 days per calendar year without medical board review. For absences exceeding 3 consecutive business days, a medical certificate (MC) must be uploaded to WorkWeek within 48 hours, and temporary email routing must be configured via ServiceImmediately.",
                entitlement_limits={
                    "outpatient_annual_limit": "14 days",
                    "hospitalization_annual_limit": "60 days",
                    "mc_upload_deadline": "Within 48 hours of return"
                },
                citation_title="View Policy Section 19.2",
                citation_url="https://hr.corp.internal/policies/19.2-medical-leave",
                tags=["medical", "sick", "doctor", "hospital", "leave", "mc", "absence"]
            )
        )

        # 4. Section 14.1: International Relocation & Transfer Allowance (UC-2.3)
        self.add_policy(
            PolicyDocument(
                section_id="14.1",
                title="Global Mobility & International Relocation Policy",
                category="RELOCATION",
                summary="Relocation benefits and facilities onboarding for international intra-company transfers.",
                details="According to Section 14.1 (International Relocation), employees approved for intra-company transfer to Tier 2 locations (including London, UK) receive a lump-sum relocation allowance of £5,000, 30 days of temporary corporate housing, and expedited facilities badge access at London - 6 Pancras Square.",
                entitlement_limits={
                    "london_allowance": "£5,000 GBP",
                    "temporary_housing": "30 days",
                    "facilities_onboarding": "Badge provisioning via ServiceImmediately"
                },
                citation_title="View Policy Section 14.1",
                citation_url="https://hr.corp.internal/policies/14.1-international-relocation",
                tags=["relocation", "transfer", "london", "allowance", "badge", "mobility", "international"]
            )
        )

    def add_policy(self, doc: PolicyDocument) -> None:
        """Add or update a policy document."""
        self._policies[doc.section_id] = doc

    def get_policy_by_section(self, section_id: str) -> Optional[PolicyDocument]:
        """Fetch policy document by exact section ID."""
        return self._policies.get(section_id)

    def search_policies(self, query: str) -> List[PolicyDocument]:
        """Search policy repository by keyword relevance."""
        q_lower = query.lower()
        matches: List[Tuple[int, PolicyDocument]] = []

        STOPWORDS = {"policy", "corporate", "company", "regarding", "what", "is", "the", "into", "office", "about", "with", "from", "for"}
        for doc in self._policies.values():
            score = 0
            # Tag match (weight 3)
            for tag in doc.tags:
                if tag in q_lower:
                    score += 3
            # Title match (weight 2)
            title_words = [w for w in doc.title.lower().split() if w not in STOPWORDS]
            if any(word in title_words for word in q_lower.split() if word not in STOPWORDS):
                score += 2
            # Body match (weight 1)
            body_words = [w for w in doc.details.lower().split() if len(w) > 4 and w not in STOPWORDS]
            if any(word in body_words for word in q_lower.split() if word not in STOPWORDS and len(word) > 4):
                score += 1

            if score >= 3:
                matches.append((score, doc))



        # Sort by score descending
        matches.sort(key=lambda x: x[0], reverse=True)
        return [doc for _, doc in matches]


# Global singleton OKF store
okf_store = OKFPolicyStore()
