# Credit Co-Pilot — hard underwriting gates.
#
# This Rego module is the production-of-record for the deterministic decline
# rules. The Python evaluator in `app/policy/gates.py` mirrors these rules
# exactly so the system runs end-to-end without OPA installed; to enable
# real OPA, set the `OPA_BIN` env var to an `opa` binary and the engine
# will shell out to `opa eval` instead.
#
# Input shape:
#   {
#     "application": { ...LoanApplication... },
#     "ratios": { "dti": <float>, "pti": <float>, "ltv": <float|null> }
#   }
#
# Output (data.credit_copilot.gates.result):
#   { "passed": bool, "violations": [ { "code": "AA-..", "reason": "..." } ] }

package credit_copilot.gates

import future.keywords.if
import future.keywords.in

default result := {"passed": true, "violations": []}

# ---- Per-state minimum contract age ----
state_min_age := {"AL": 19, "NE": 19, "MS": 21}

min_age(state) := age if {
	age := state_min_age[state]
} else := 18

# ---- Violations ----
violations contains v if {
	input.application.sanctions_hit == true
	v := {"code": "AA-14", "reason": "OFAC / sanctions hit"}
}

violations contains v if {
	input.application.fraud_flag == true
	v := {"code": "AA-14", "reason": "Active fraud flag"}
}

violations contains v if {
	input.application.age < min_age(input.application.state)
	v := {
		"code": "AA-12",
		"reason": sprintf("Age %d below state minimum %d for %s",
			[input.application.age, min_age(input.application.state), input.application.state]),
	}
}

violations contains v if {
	input.application.bureau.bankruptcies_7y >= 2
	v := {"code": "AA-09", "reason": "Two or more bankruptcies in last 7 years"}
}

violations contains v if {
	input.application.bureau.delinquencies_24m >= 3
	v := {"code": "AA-03", "reason": "Three or more delinquencies in last 24 months"}
}

# DTI hard caps by product
dti_caps := {
	"personal_loan": 0.50,
	"auto": 0.55,
	"mortgage": 0.50,
	"sm_business": 0.55,
}

violations contains v if {
	cap := dti_caps[input.application.product]
	input.ratios.dti > cap
	v := {
		"code": "AA-06",
		"reason": sprintf("DTI %.2f exceeds hard cap %.2f for %s",
			[input.ratios.dti, cap, input.application.product]),
	}
}

# LTV hard cap on secured products
ltv_caps := {"auto": 1.25, "mortgage": 1.05}

violations contains v if {
	cap := ltv_caps[input.application.product]
	input.ratios.ltv > cap
	v := {
		"code": "AA-10",
		"reason": sprintf("LTV %.2f exceeds hard cap %.2f for %s",
			[input.ratios.ltv, cap, input.application.product]),
	}
}

# ---- Final result ----
result := {"passed": count(violations) == 0, "violations": [v | v := violations[_]]}
