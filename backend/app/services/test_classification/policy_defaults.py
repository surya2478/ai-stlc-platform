"""Built-in automation-classification policy and editable rule metadata."""

from copy import deepcopy

CLASSIFICATION_CHECKS = {
    "unresolved_requirement": "Requirement or scenario is not approved",
    "missing_expected_result": "Expected result or test steps are missing",
    "production_only": "Test is production-only or destructive",
    "unsupported_application": "Application mapping is missing or inactive",
    "test_data_not_ready": "Required test data is not ready",
    "unstable_ui": "The user interface is marked unstable",
    "scenario_not_approved": "Linked scenario is not approved",
    "optional_validator_unavailable": "An optional validator is unavailable",
}

AUTOMATION_VALUE_WEIGHT_KEYS = {
    "expected_result_determinism",
    "regression_value",
    "reusability",
    "manual_effort",
    "business_criticality",
}
COMPLEXITY_WEIGHT_KEYS = {
    "step_count",
    "external_dependency_count",
    "test_data_volume",
    "precondition_count",
}

DEFAULT_CLASSIFICATION_POLICY_RULES = {
    "manual_only_conditions": [
        {
            "code": "captcha",
            "label": "CAPTCHA challenge",
            "keywords": ["captcha", "recaptcha", "hcaptcha"],
            "metadata_flags": ["captcha_dependency"],
            "reason": "CAPTCHA requires human verification and cannot be completed by unattended automation.",
        },
        {
            "code": "otp",
            "label": "OTP verification",
            "keywords": ["otp", "one-time password", "one time password", "sms code"],
            "metadata_flags": ["otp_dependency"],
            "reason": "OTP depends on a secure out-of-band code and requires controlled human handling.",
        },
        {
            "code": "biometrics",
            "label": "Biometric verification",
            "keywords": ["biometric", "fingerprint", "face id", "facial recognition", "iris scan"],
            "metadata_flags": ["biometric_dependency"],
            "reason": "Biometric identity checks require a physical person or approved specialist hardware.",
        },
        {
            "code": "kiosk",
            "label": "Physical kiosk",
            "keywords": ["kiosk", "self-service terminal"],
            "metadata_flags": ["kiosk_dependency"],
            "reason": "This test depends on physical kiosk hardware that is unavailable to unattended automation.",
        },
        {
            "code": "atm",
            "label": "ATM machine",
            "keywords": ["atm", "cash machine", "automated teller"],
            "metadata_flags": ["atm_dependency"],
            "reason": "This test depends on physical ATM hardware and must follow a controlled manual process.",
        },
    ],
    "candidate_rules": {
        "block_if": ["unresolved_requirement", "missing_expected_result", "production_only"],
        "conditional_if": [
            "unsupported_application",
            "test_data_not_ready",
            "unstable_ui",
            "optional_validator_unavailable",
        ],
        "minimum_automation_value_score": 60,
    },
    "routing_rules": [
        {"when": {}, "primary_adapter": "PLAYWRIGHT_MCP", "supporting_adapters": []}
    ],
    "external_validation_rules": [{"required": [], "optional": []}],
    "evidence_rules": {
        "web_e2e": {
            "mandatory": [
                "SCREENSHOT",
                "DOM_SNAPSHOT",
                "NETWORK_TRACE",
                "STEP_RESULT",
                "BUSINESS_ASSERTION",
            ]
        }
    },
    "scoring_weights": {
        "automation_value": {
            "expected_result_determinism": 25,
            "regression_value": 20,
            "reusability": 15,
            "manual_effort": 20,
            "business_criticality": 20,
        },
        "complexity": {
            "step_count": 30,
            "external_dependency_count": 30,
            "test_data_volume": 20,
            "precondition_count": 20,
        },
    },
}


def default_policy_rules() -> dict:
    return deepcopy(DEFAULT_CLASSIFICATION_POLICY_RULES)
