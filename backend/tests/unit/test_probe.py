from whaleproof.commands.probe import render_matrix


def test_render_matrix_has_row_per_result_and_no_values():
    md = render_matrix([
        {"name": "gex_levels", "when": "2025-09-25", "status": 200, "rows": 1,
         "keys": ["call_wall", "put_wall"], "first_date": "2025-09-25", "last_date": "2025-09-25", "error": ""},
        {"name": "unusualness", "when": "today", "status": 403, "rows": 0, "keys": [],
         "first_date": "", "last_date": "", "error": "forbidden"},
    ])
    assert "| gex_levels | 2025-09-25 | 200 | 1 |" in md
    assert "| unusualness | today | 403 | 0 |" in md
    assert "call_wall, put_wall" in md
