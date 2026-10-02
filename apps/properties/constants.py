"""Fixed choices and validators for the portfolio."""

from django.core.validators import RegexValidator
from django.db import models


class USState(models.TextChoices):
    """US states plus the District of Columbia, as two-letter codes."""

    AL = "AL", "Alabama"
    AK = "AK", "Alaska"
    AZ = "AZ", "Arizona"
    AR = "AR", "Arkansas"
    CA = "CA", "California"
    CO = "CO", "Colorado"
    CT = "CT", "Connecticut"
    DE = "DE", "Delaware"
    DC = "DC", "District of Columbia"
    FL = "FL", "Florida"
    GA = "GA", "Georgia"
    HI = "HI", "Hawaii"
    ID = "ID", "Idaho"
    IL = "IL", "Illinois"
    IN = "IN", "Indiana"
    IA = "IA", "Iowa"
    KS = "KS", "Kansas"
    KY = "KY", "Kentucky"
    LA = "LA", "Louisiana"
    ME = "ME", "Maine"
    MD = "MD", "Maryland"
    MA = "MA", "Massachusetts"
    MI = "MI", "Michigan"
    MN = "MN", "Minnesota"
    MS = "MS", "Mississippi"
    MO = "MO", "Missouri"
    MT = "MT", "Montana"
    NE = "NE", "Nebraska"
    NV = "NV", "Nevada"
    NH = "NH", "New Hampshire"
    NJ = "NJ", "New Jersey"
    NM = "NM", "New Mexico"
    NY = "NY", "New York"
    NC = "NC", "North Carolina"
    ND = "ND", "North Dakota"
    OH = "OH", "Ohio"
    OK = "OK", "Oklahoma"
    OR = "OR", "Oregon"
    PA = "PA", "Pennsylvania"
    RI = "RI", "Rhode Island"
    SC = "SC", "South Carolina"
    SD = "SD", "South Dakota"
    TN = "TN", "Tennessee"
    TX = "TX", "Texas"
    UT = "UT", "Utah"
    VT = "VT", "Vermont"
    VA = "VA", "Virginia"
    WA = "WA", "Washington"
    WV = "WV", "West Virginia"
    WI = "WI", "Wisconsin"
    WY = "WY", "Wyoming"


ZIP_CODE_VALIDATOR = RegexValidator(
    r"^\d{5}(-\d{4})?$",
    "Enter a 5 or 9 digit ZIP code, for example 62704 or 62704-1234.",
)


class PropertyType(models.TextChoices):
    """What kind of space a building holds.

    The designation belongs to the **property**, not to each unit: a building is
    residential or commercial and its units inherit that. Bedrooms and bathrooms
    describe residential space, so they are only meaningful in a residential
    property (enforced in the unit form and reflected in the screens).
    """

    RESIDENTIAL = "RESIDENTIAL", "Residential"
    COMMERCIAL = "COMMERCIAL", "Commercial"


#: The amenities every new RHP database starts with. Editable in the back office.
DEFAULT_AMENITIES = (
    "Parking",
    "Off-street parking",
    "Laundry in unit",
    "Laundry in building",
    "Dishwasher",
    "Air conditioning",
    "Balcony or patio",
    "Storage",
    "Fireplace",
    "Furnished",
    "Pet friendly",
    "Elevator",
    "Gym",
    "Pool",
    "Security system",
    "Utilities included",
    "Wheelchair accessible",
)


#: Upload limits for property banners.
BANNER_ALLOWED_CONTENT_TYPES = frozenset({"image/jpeg", "image/png", "image/webp"})
BANNER_MAX_DIMENSION = 6000
