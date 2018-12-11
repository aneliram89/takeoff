from enum import Enum, auto

from typing import Dict

from runway.KeyVaultSecrets import KeyVaultSecrets, Secret


class CommonCredentials(Enum):
    subscription_id = auto()
    azure_username = auto()
    azure_password = auto()
    azure_databricks_host = auto()
    azure_databricks_token = auto()
    azure_shared_blob_username = auto()
    azure_shared_blob_password = auto()
    registry_username = auto()
    registry_password = auto()

def find_secret(common, secrets: Dict[str, Secret]):
    if common not in secrets:
        raise ValueError(f"Could not find required key {common}")
    return secrets[common]

def common_credentials(dtap):
    secrets = KeyVaultSecrets.get_keyvault_secrets(dtap, 'common')
    indexed = {_.key: _ for _ in secrets}
    return {_: find_secret(_, indexed) for _ in CommonCredentials}

