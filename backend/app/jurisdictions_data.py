"""Seed registry of the 50 states + Washington, D.C. unclaimed-property programs.

IMPORTANT -- PROVENANCE
-----------------------
The agency names and portal URLs below are a *starting seed* compiled from
general knowledge. They are NOT legally verified. Every jurisdiction is seeded
with ``compliance_review_status = "unverified_seed"`` and
``operating_status = "not_cleared"``. The ``jurisdiction_portal_check`` job
fetches every URL and records reachability/changes; the Compliance Analyst
raises alerts for any jurisdiction whose rules have not been verified.

Finder licensing, fee caps, waiting periods, authorization/contract rules and
statutory references are intentionally left blank ("needs research") so that
nothing in the system asserts a legal rule that a human has not confirmed from
the official statute or agency guidance. Cross-reference sources:
  * NAUPA state directory: https://unclaimed.org/search-property/
  * MissingMoney (multi-state search): https://www.missingmoney.com/
"""
from __future__ import annotations

NAUPA_DIRECTORY = "https://unclaimed.org/search-property/"
MISSING_MONEY = "https://www.missingmoney.com/"

# code, name, agency, agency_url, search_portal_url
JURISDICTIONS: list[tuple[str, str, str, str, str]] = [
    ("AL", "Alabama", "Alabama State Treasury - Unclaimed Property Division", "https://treasury.alabama.gov/unclaimed-property/", "https://alabama.findyourunclaimedproperty.com/"),
    ("AK", "Alaska", "Alaska Department of Revenue - Treasury Division, Unclaimed Property", "https://unclaimedproperty.alaska.gov/", "https://unclaimedproperty.alaska.gov/"),
    ("AZ", "Arizona", "Arizona Department of Revenue - Unclaimed Property Unit", "https://azdor.gov/unclaimed-property", "https://azdor.gov/unclaimed-property"),
    ("AR", "Arkansas", "Arkansas Auditor of State - Unclaimed Property", "https://www.auditor.ar.gov/", "https://www.claimitar.gov/"),
    ("CA", "California", "California State Controller's Office - Unclaimed Property Division", "https://www.sco.ca.gov/upd_msg.html", "https://ucpi.sco.ca.gov/"),
    ("CO", "Colorado", "Colorado Department of the Treasury - Great Colorado Payback", "https://treasury.colorado.gov/unclaimed-property", "https://colorado.findyourunclaimedproperty.com/"),
    ("CT", "Connecticut", "Connecticut Office of the State Treasurer - Unclaimed Property", "https://portal.ct.gov/ott", "https://ctbiglist.com/"),
    ("DE", "Delaware", "Delaware Department of Finance - Office of Unclaimed Property", "https://unclaimedproperty.delaware.gov/", "https://unclaimedproperty.delaware.gov/"),
    ("DC", "District of Columbia", "DC Office of the Chief Financial Officer - Unclaimed Property Unit", "https://cfo.dc.gov/service/unclaimed-property", "https://dc.findyourunclaimedproperty.com/"),
    ("FL", "Florida", "Florida Department of Financial Services - Division of Unclaimed Property", "https://www.myfloridacfo.com/division/unclaimedproperty", "https://www.fltreasurehunt.gov/"),
    ("GA", "Georgia", "Georgia Department of Revenue - Unclaimed Property Program", "https://dor.georgia.gov/unclaimed-property-program", "https://dor.georgia.gov/unclaimed-property-program"),
    ("HI", "Hawaii", "Hawaii Department of Budget and Finance - Unclaimed Property Program", "https://unclaimedproperty.ehawaii.gov/", "https://unclaimedproperty.ehawaii.gov/"),
    ("ID", "Idaho", "Idaho State Treasurer - Unclaimed Property", "https://sto.idaho.gov/", "https://yourmoney.idaho.gov/"),
    ("IL", "Illinois", "Illinois State Treasurer - Unclaimed Property (I-Cash)", "https://illinoistreasurer.gov/", "https://icash.illinoistreasurer.gov/"),
    ("IN", "Indiana", "Indiana Attorney General - Unclaimed Property Division", "https://www.in.gov/attorneygeneral/", "https://indianaunclaimed.gov/"),
    ("IA", "Iowa", "Iowa State Treasurer - Great Iowa Treasure Hunt", "https://www.iowatreasurer.gov/", "https://greatiowatreasurehunt.gov/"),
    ("KS", "Kansas", "Kansas State Treasurer - Unclaimed Property", "https://www.kansasstatetreasurer.com/", "https://kansascash.ks.gov/"),
    ("KY", "Kentucky", "Kentucky State Treasury - Unclaimed Property", "https://treasury.ky.gov/unclaimedproperty", "https://treasury.ky.gov/unclaimedproperty"),
    ("LA", "Louisiana", "Louisiana Department of Treasury - Unclaimed Property", "https://www.treasury.la.gov/unclaimed-property", "https://www.treasury.la.gov/unclaimed-property"),
    ("ME", "Maine", "Maine Office of the State Treasurer - Unclaimed Property", "https://www.maine.gov/unclaimedproperty", "https://www.maine.gov/unclaimedproperty"),
    ("MD", "Maryland", "Comptroller of Maryland - Unclaimed Property", "https://www.marylandtaxes.gov/unclaimed-property/", "https://interactive.marylandtaxes.gov/Individuals/Unclaim/default.aspx"),
    ("MA", "Massachusetts", "Massachusetts Treasurer and Receiver General - Unclaimed Property Division", "https://www.mass.gov/orgs/unclaimed-property-division", "https://findmassmoney.com/"),
    ("MI", "Michigan", "Michigan Department of Treasury - Unclaimed Property", "https://www.michigan.gov/treasury", "https://unclaimedproperty.michigan.gov/"),
    ("MN", "Minnesota", "Minnesota Department of Commerce - Unclaimed Property", "https://mn.gov/commerce/money/unclaimed-property/", "https://minnesota.findyourunclaimedproperty.com/"),
    ("MS", "Mississippi", "Mississippi State Treasurer - Unclaimed Property", "https://treasury.ms.gov/unclaimed-property/", "https://treasury.ms.gov/unclaimed-property/"),
    ("MO", "Missouri", "Missouri State Treasurer - Unclaimed Property", "https://treasurer.mo.gov/unclaimedproperty", "https://treasurer.mo.gov/unclaimedproperty"),
    ("MT", "Montana", "Montana Department of Revenue - Unclaimed Property", "https://mtrevenue.gov/unclaimed-property/", "https://mtrevenue.gov/unclaimed-property/"),
    ("NE", "Nebraska", "Nebraska State Treasurer - Unclaimed Property", "https://treasurer.nebraska.gov/up/", "https://treasurer.nebraska.gov/up/"),
    ("NV", "Nevada", "Nevada State Treasurer - Unclaimed Property", "https://www.nevadatreasurer.gov/UnclaimedProperty/", "https://www.nevadatreasurer.gov/UnclaimedProperty/"),
    ("NH", "New Hampshire", "New Hampshire Treasury - Abandoned & Unclaimed Property", "https://www.nh.gov/treasury/", "https://www.nh.gov/treasury/"),
    ("NJ", "New Jersey", "New Jersey Department of the Treasury - Unclaimed Property Administration", "https://unclaimedfunds.nj.gov/app/", "https://unclaimedfunds.nj.gov/app/"),
    ("NM", "New Mexico", "New Mexico Taxation and Revenue Department - Unclaimed Property", "https://www.tax.newmexico.gov/", "https://www.tax.newmexico.gov/"),
    ("NY", "New York", "Office of the New York State Comptroller - Office of Unclaimed Funds", "https://www.osc.ny.gov/unclaimed-funds", "https://www.osc.ny.gov/unclaimed-funds"),
    ("NC", "North Carolina", "North Carolina Department of State Treasurer - Unclaimed Property Program", "https://www.nctreasurer.com/", "https://www.nccash.com/"),
    ("ND", "North Dakota", "North Dakota Department of Trust Lands - Unclaimed Property", "https://www.land.nd.gov/", "https://unclaimedproperty.nd.gov/"),
    ("OH", "Ohio", "Ohio Department of Commerce - Division of Unclaimed Funds", "https://unclaimedfunds.ohio.gov/", "https://unclaimedfunds.ohio.gov/"),
    ("OK", "Oklahoma", "Oklahoma State Treasurer - Unclaimed Property", "https://oklahoma.gov/treasurer.html", "https://oklahoma.findyourunclaimedproperty.com/"),
    ("OR", "Oregon", "Oregon Department of State Lands - Unclaimed Property", "https://www.oregon.gov/dsl/", "https://unclaimed.oregon.gov/"),
    ("PA", "Pennsylvania", "Pennsylvania Treasury - Bureau of Unclaimed Property", "https://www.patreasury.gov/unclaimed-property/", "https://www.patreasury.gov/unclaimed-property/"),
    ("RI", "Rhode Island", "Rhode Island Office of the General Treasurer - Unclaimed Property", "https://treasury.ri.gov/", "https://www.findrimoney.com/"),
    ("SC", "South Carolina", "South Carolina State Treasurer - Unclaimed Property Program", "https://treasurer.sc.gov/", "https://treasurer.sc.gov/"),
    ("SD", "South Dakota", "South Dakota State Treasurer - Unclaimed Property", "https://sdtreasurer.gov/", "https://sdtreasurer.gov/"),
    ("TN", "Tennessee", "Tennessee Department of Treasury - Unclaimed Property", "https://treasury.tn.gov/Unclaimed-Property", "https://treasury.tn.gov/Unclaimed-Property"),
    ("TX", "Texas", "Texas Comptroller of Public Accounts - Unclaimed Property", "https://comptroller.texas.gov/programs/claimittexas/", "https://www.claimittexas.gov/"),
    ("UT", "Utah", "Utah State Treasurer - Unclaimed Property Division", "https://treasurer.utah.gov/", "https://mycash.utah.gov/"),
    ("VT", "Vermont", "Vermont Office of the State Treasurer - Unclaimed Property", "https://www.vermonttreasurer.gov/", "https://www.vermonttreasurer.gov/"),
    ("VA", "Virginia", "Virginia Department of the Treasury - Unclaimed Property", "https://www.trs.virginia.gov/", "https://www.vamoneysearch.gov/"),
    ("WA", "Washington", "Washington Department of Revenue - Unclaimed Property", "https://dor.wa.gov/", "https://ucp.dor.wa.gov/"),
    ("WV", "West Virginia", "West Virginia State Treasurer - Unclaimed Property", "https://wvtreasury.com/", "https://wvtreasury.com/"),
    ("WI", "Wisconsin", "Wisconsin Department of Revenue - Unclaimed Property", "https://www.revenue.wi.gov/", "https://www.revenue.wi.gov/"),
    ("WY", "Wyoming", "Wyoming State Treasurer - Unclaimed Property", "https://statetreasurer.wyo.gov/", "https://mypropertyreturn.wyo.gov/"),
]

NEEDS_RESEARCH = "Needs research - not yet verified against statute or agency guidance."

assert len(JURISDICTIONS) == 51, len(JURISDICTIONS)
assert len({j[0] for j in JURISDICTIONS}) == 51
