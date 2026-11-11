"""The public half of the release signing key: the app only trusts update lists signed by the matching private key.
(The release key. Its private half is the repository secret TTA_UPDATE_KEY and a backup file kept outside the repo; never commit it.)"""
PUBLIC_KEY_HEX = "7f19a76fe5bd05b700545164589ff5e34bfda512e9e1d44d4e3ca14e2ec388ed"
