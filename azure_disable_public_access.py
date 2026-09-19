#!/usr/bin/env python3
from cortexutils.responder import Responder
from azure.identity import ClientSecretCredential
from azure.mgmt.storage import StorageManagementClient
from azure.mgmt.storage.models import StorageAccountUpdateParameters
from azure.core.exceptions import HttpResponseError, ResourceNotFoundError
import re

RESOURCE_ID_RE = re.compile(
    r"^/subscriptions/(?P<sub>[^/]+)/resourceGroups/(?P<rg>[^/]+)"
    r"/providers/Microsoft\.Storage/storageAccounts/(?P<name>[^/]+)$",
    re.IGNORECASE,
)


class AzureDisableBlobPublicAccessResponder(Responder):
    def __init__(self):
        Responder.__init__(self)
        self.tenant_id = self.get_param("config.azure_tenant_id", None, "Missing Azure tenant ID")
        self.client_id = self.get_param("config.azure_client_id", None, "Missing Azure client ID")
        self.client_secret = self.get_param("config.azure_client_secret", None, "Missing Azure client secret")
        self.subscription_id = self.get_param("config.azure_subscription_id", None, "Missing Azure subscription ID")
        self.default_resource_group = self.get_param("config.default_resource_group", None)

    def resolve_target(self, raw_value):
        """Accepts a full ARM resource ID, 'resourceGroup/accountName', or a bare
        account name (requires default_resource_group to be configured).

        When invoked by TheHive against an observable (thehive:case_artifact),
        Cortex passes the full observable entity as a dict rather than the bare
        value string - unwrap it to get the actual observable data."""
        if isinstance(raw_value, dict):
            raw_value = raw_value.get("data")
        value = str(raw_value).strip()

        m = RESOURCE_ID_RE.match(value)
        if m:
            return m.group("sub"), m.group("rg"), m.group("name")

        if "/" in value:
            rg, name = value.split("/", 1)
            return self.subscription_id, rg, name

        if self.default_resource_group:
            return self.subscription_id, self.default_resource_group, value

        self.error(
            "Could not determine resource group for storage account '%s'. "
            "Provide a full ARM resource ID, 'resourceGroup/accountName', "
            "or configure default_resource_group." % value
        )

    def run(self):
        Responder.run(self)

        raw_value = self.get_data()
        sub_id, rg, account_name = self.resolve_target(raw_value)

        credential = ClientSecretCredential(
            tenant_id=self.tenant_id,
            client_id=self.client_id,
            client_secret=self.client_secret,
        )
        client = StorageManagementClient(credential, sub_id)

        try:
            account = client.storage_accounts.get_properties(rg, account_name)
        except ResourceNotFoundError:
            self.error("Storage account '%s' not found in resource group '%s'" % (account_name, rg))
            return

        was_public = bool(account.allow_blob_public_access)

        try:
            client.storage_accounts.update(
                rg, account_name,
                StorageAccountUpdateParameters(allow_blob_public_access=False),
            )
        except HttpResponseError as e:
            self.error("Azure API error disabling public access: %s" % e.message)
            return

        full_response = {
            "action": "disable-blob-public-access",
            "subscriptionId": sub_id,
            "resourceGroup": rg,
            "storageAccount": account_name,
            "wasPubliclyAccessible": was_public,
            "nowDisabled": True,
        }
        self.report(full_response)

    def operations(self, raw):
        return [self.build_operation("AddTagToCase", tag="azure:public-access-disabled")]


if __name__ == "__main__":
    AzureDisableBlobPublicAccessResponder().run()
