from urllib.parse import parse_qs, urlparse

from isso_facilita.app import render_dashboard


def test_dashboard_builds_whatsapp_share_link() -> None:
    page = render_dashboard(
        [
            {
                "marketplace": "shopee",
                "title": "SSD <rápido>",
                "message": "Oferta SSD\nhttps://example.com/affiliate?a=1&b=2",
                "published_at": "2026-10-13 15:00:00",
            }
        ]
    )

    assert "SSD &lt;rápido&gt;" in page
    assert "Compartilhar no WhatsApp" in page
    href = page.split('href="', 1)[1].split('"', 1)[0].replace("&amp;", "&")
    assert parse_qs(urlparse(href).query)["text"] == [
        "Oferta SSD\nhttps://example.com/affiliate?a=1&b=2"
    ]
