"""Built-in Workday employer fallback used when the YAML registry is missing."""

_BUILTIN_EMPLOYERS: dict[str, dict] = {
    # Big Tech / FAANG+
    "nvidia": {
        "name": "NVIDIA",
        "tenant": "nvidia",
        "site_id": "NVIDIAExternalCareerSite",
        "base_url": "https://nvidia.wd5.myworkdayjobs.com",
    },
    "salesforce": {
        "name": "Salesforce",
        "tenant": "salesforce",
        "site_id": "External_Career_Site",
        "base_url": "https://salesforce.wd12.myworkdayjobs.com",
    },
    "netflix": {
        "name": "Netflix",
        "tenant": "netflix",
        "site_id": "Netflix",
        "base_url": "https://netflix.wd1.myworkdayjobs.com",
    },
    "adobe": {
        "name": "Adobe",
        "tenant": "adobe",
        "site_id": "external_experienced",
        "base_url": "https://adobe.wd5.myworkdayjobs.com",
    },
    "cisco": {
        "name": "Cisco",
        "tenant": "cisco",
        "site_id": "Cisco_Careers",
        "base_url": "https://cisco.wd5.myworkdayjobs.com",
    },
    "paypal": {
        "name": "PayPal",
        "tenant": "paypal",
        "site_id": "jobs",
        "base_url": "https://paypal.wd1.myworkdayjobs.com",
    },
    "intel": {
        "name": "Intel",
        "tenant": "intel",
        "site_id": "External",
        "base_url": "https://intel.wd1.myworkdayjobs.com",
    },
    "workday": {
        "name": "Workday",
        "tenant": "workday",
        "site_id": "Workday",
        "base_url": "https://workday.wd5.myworkdayjobs.com",
    },
    "mastercard": {
        "name": "Mastercard",
        "tenant": "mastercard",
        "site_id": "CorporateCareers",
        "base_url": "https://mastercard.wd1.myworkdayjobs.com",
    },
    # Tech / Enterprise
    "servicenow": {
        "name": "ServiceNow",
        "tenant": "servicenow",
        "site_id": "Careers",
        "base_url": "https://servicenow.wd1.myworkdayjobs.com",
    },
    "vmware": {
        "name": "VMware (Broadcom)",
        "tenant": "broadcom",
        "site_id": "Broadcom",
        "base_url": "https://broadcom.wd1.myworkdayjobs.com",
    },
    "uber": {
        "name": "Uber",
        "tenant": "uber",
        "site_id": "Uber_Careers",
        "base_url": "https://uber.wd5.myworkdayjobs.com",
    },
    "snap": {
        "name": "Snap",
        "tenant": "snap",
        "site_id": "Snap",
        "base_url": "https://snap.wd5.myworkdayjobs.com",
    },
    "target": {
        "name": "Target",
        "tenant": "target",
        "site_id": "TargetCareers",
        "base_url": "https://target.wd5.myworkdayjobs.com",
    },
    "capitalone": {
        "name": "Capital One",
        "tenant": "capitalone",
        "site_id": "Capital_One",
        "base_url": "https://capitalone.wd12.myworkdayjobs.com",
    },
    "jpmorgan": {
        "name": "JPMorgan Chase",
        "tenant": "jpmorgan",
        "site_id": "JPMorgan_Careers",
        "base_url": "https://jpmc.wd5.myworkdayjobs.com",
    },
    "visa": {
        "name": "Visa",
        "tenant": "visa",
        "site_id": "Visa_Careers",
        "base_url": "https://visa.wd12.myworkdayjobs.com",
    },
    "square": {
        "name": "Block (Square)",
        "tenant": "block",
        "site_id": "Block",
        "base_url": "https://block.wd1.myworkdayjobs.com",
    },
    "motorola": {
        "name": "Motorola Solutions",
        "tenant": "motorolasolutions",
        "site_id": "Careers",
        "base_url": "https://motorolasolutions.wd5.myworkdayjobs.com",
    },
    # Ride-hailing / Delivery / Marketplace
    "lyft": {
        "name": "Lyft",
        "tenant": "lyft",
        "site_id": "Lyft",
        "base_url": "https://lyft.wd5.myworkdayjobs.com",
    },
    "pinterest": {
        "name": "Pinterest",
        "tenant": "pinterestinc",
        "site_id": "PinterestCareers",
        "base_url": "https://pinterestinc.wd1.myworkdayjobs.com",
    },
    "instacart": {
        "name": "Instacart",
        "tenant": "instacart",
        "site_id": "Instacart",
        "base_url": "https://instacart.wd5.myworkdayjobs.com",
    },
    "doordash": {
        "name": "DoorDash",
        "tenant": "doordash",
        "site_id": "DoorDash",
        "base_url": "https://doordash.wd5.myworkdayjobs.com",
    },
    # Media / Entertainment
    "spotify": {
        "name": "Spotify",
        "tenant": "spotify",
        "site_id": "Spotify",
        "base_url": "https://spotify.wd5.myworkdayjobs.com",
    },
    # Banking / Finance — slug needs verification
    "goldmansachs": {
        "name": "Goldman Sachs",
        "tenant": "gsjobs",
        "site_id": "GOLDMANSACHSJOBS",
        "base_url": "https://gs.wd5.myworkdayjobs.com",
    },
}
