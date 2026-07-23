

def test_generate_slugs_tries_com_suffix():
    """BILL's greenhouse token is billcom; the com suffix must be probed."""
    from app.services.watchlist_service import _generate_slugs

    slugs = _generate_slugs("BILL")
    assert "billcom" in slugs
    assert slugs.index("bill") < slugs.index("billcom")
