"""Ticker page company header: name and description from UW's cached stock info, tidied for display."""
from whaleproof.core.data_layer.fetch import cache_key
from whaleproof.core.data_layer.store import Store
from whaleproof.desk.company import company_info, tidy_description, tidy_name


def test_all_caps_names_become_title_case_keeping_acronyms():
    assert tidy_name("GUIDEWIRE SOFTWARE") == "Guidewire Software"
    assert tidy_name("HEWLETT PACKARD ENTERPRISE") == "Hewlett Packard Enterprise"
    assert tidy_name("NVIDIA") == "NVIDIA"
    assert tidy_name("SPDR(R) S&P(R) OIL & GAS EXPLORATION & PRODUCTION ETF") == "SPDR S&P Oil & Gas Exploration & Production ETF"
    assert tidy_name("ISHARES 20+ YEAR TREASURY BOND ETF") == "iShares 20+ Year Treasury Bond ETF"
    assert tidy_name("T-MOBILE US") == "T-Mobile US"
    assert tidy_name("D-WAVE QUANTUM") == "D-Wave Quantum"
    assert tidy_name("MERCK & CO") == "Merck & Co"
    assert tidy_name("PG&E") == "PG&E"
    assert tidy_name("HUT 8 MINING") == "Hut 8 Mining"
    assert tidy_name("KKR & CO") == "KKR & Co"


def test_mixed_case_and_empty_names_left_alone():
    assert tidy_name("SK hynix Inc. ADR") == "SK hynix Inc. ADR"
    assert tidy_name("-") is None
    assert tidy_name("") is None and tidy_name(None) is None


def test_descriptions_get_sentence_case_and_a_real_ellipsis():
    d = ("guidewire delivers the software that insurers need to adapt. we combine three ...")
    assert tidy_description(d) == "Guidewire delivers the software that insurers need to adapt. We combine three…"
    assert tidy_description("Nvidia is a chip maker.") == "Nvidia is a chip maker."
    assert tidy_description("") is None and tidy_description(None) is None


def test_company_info_reads_the_cache_only(tmp_path):
    store = Store(tmp_path / "c.sqlite")
    assert company_info(store, "GWRE") is None
    store.cache_put(cache_key("/api/stock/GWRE/info", {}), "/api/stock/GWRE/info",
                    {"data": {"symbol": "GWRE", "full_name": "GUIDEWIRE SOFTWARE",
                              "short_description": "guidewire delivers software."}})
    assert company_info(store, "GWRE") == {"name": "Guidewire Software",
                                           "description": "Guidewire delivers software."}


def test_no_capital_after_an_abbreviation():
    assert tidy_description("Alphabet Inc. is an American company. it was created through ...") == \
        "Alphabet Inc. is an American company. It was created through…"
    assert tidy_description("Based in the U.S. and Canada.") == "Based in the U.S. and Canada."
