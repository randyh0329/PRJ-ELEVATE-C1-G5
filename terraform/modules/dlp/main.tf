# Cloud DLP Multi-Region De-identification Templates (SDD §4.10)

resource "google_data_loss_prevention_deidentify_template" "elevate_dlp_primary" {
  parent       = "projects/${var.project_id}/locations/${var.primary_region}"
  display_name = "Elevate HR DLP De-identification Template (Primary)"
  template_id  = "elevate-hr-dlp-template-v1-${var.primary_region}"

  deidentify_config {
    info_type_transformations {
      # Hard Redactions for Financial/SSN SPII
      transformations {
        info_types { name = "US_SOCIAL_SECURITY_NUMBER" }
        info_types { name = "CREDIT_CARD_NUMBER" }
        info_types { name = "BANK_ACCOUNT_NUMBER" }
        info_types { name = "IBAN_CODE" }
        info_types { name = "PASSPORT" }

        primitive_transformation {
          replace_with_info_type_config = true
        }
      }

      # Crypto-Deterministic Pseudonymization for Operational Identifiers
      transformations {
        info_types { name = "PERSON_NAME" }
        info_types { name = "PHONE_NUMBER" }
        info_types { name = "EMAIL_ADDRESS" }
        info_types { name = "STREET_ADDRESS" }

        primitive_transformation {
          replace_config {
            new_value {
              string_value = "[SURROGATE_PSEUDONYMIZED]"
            }
          }
        }
      }
    }
  }
}

output "primary_dlp_template_name" {
  value = google_data_loss_prevention_deidentify_template.elevate_dlp_primary.name
}
