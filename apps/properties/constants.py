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


class UnitType(models.TextChoices):
    """What kind of space a unit is.

    Bedrooms and bathrooms describe residential space, so they are only
    meaningful for RESIDENTIAL units (enforced in the unit form and reflected in
    the unit screens).
    """

    RESIDENTIAL = "RESIDENTIAL", "Residential"
    COMMERCIAL = "COMMERCIAL", "Commercial"


#: Upload limits for property banners.
BANNER_ALLOWED_CONTENT_TYPES = frozenset({"image/jpeg", "image/png", "image/webp"})
BANNER_MAX_DIMENSION = 6000
