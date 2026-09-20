# Forensic encryptor policy — ADR-014, Block A-3.
# Least privilege: only transit encrypt/decrypt for the forensic key.
path "transit/encrypt/forensic-aes256-gcm" {
  capabilities = ["update"]
}

path "transit/decrypt/forensic-aes256-gcm" {
  capabilities = ["update"]
}