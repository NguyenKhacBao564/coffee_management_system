"""Verified S03a synthetic events, identified individually without changing source.

Evidence: Windows CSV SHA-256
2f8ab406786ee482afb409ad4014f077dd8126a50ad3b43cb1e606e57a7b3416,
independently reconciled with application PostgreSQL on 2026-10-06.
This allowlist does not classify other readings by this agent as test data.
"""

S03A_AGENT_ID = "06c70368-50a1-470d-bf26-45391cd05069"
S03A_EVENT_IDS = frozenset({
    "1f9fc74f-8ba2-4275-b459-b077c35696cb",
    "3de5bcf6-8597-4dd6-b456-7b1661b1adbc",
    "6c50e5b2-b0c1-4a41-a29d-f8117d36b365",
    "ea3da884-d74f-48b2-8a9b-81240ed63ccd",
    "533c1b84-fa27-47b3-8da8-78c8522809f1",
    "cb9196f9-f319-464f-a760-70590180fbb2",
    "8ac70c98-77d1-46b8-98b4-b7467221d025",
    "16d86ac7-44cb-40c7-8398-28d8839ec1d9",
    "496c5b22-2a45-4565-8810-8dc5e725b354",
})


def is_acceptance_test(agent_id: str, event_id: str) -> bool:
    return agent_id == S03A_AGENT_ID and event_id in S03A_EVENT_IDS
