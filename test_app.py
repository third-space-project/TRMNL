from app import get_nearby_aircraft


def test_nearby_aircraft_includes_position_data(monkeypatch):
    def fake_get(url, params, headers, timeout):
        class FakeResponse:
            status_code = 200

            def json(self):
                return {
                    "states": [
                        [
                            "abc123",
                            "AAL123 ",
                            "United States",
                            1710000000,
                            1710000000,
                            -122.4,
                            47.6,
                            11000,
                            False,
                            500,
                            180,
                            0,
                            None,
                            None,
                            None,
                            None,
                            None,
                            None,
                            None,
                            None,
                            None,
                        ]
                    ]
                }

        return FakeResponse()

    monkeypatch.setattr("app.requests.get", fake_get)
    monkeypatch.setattr(
        "app.get_airport_info",
        lambda code: {"lat": 47.6, "lon": -122.4, "name": "Test Airport"},
    )

    result = get_nearby_aircraft("SEA", radius=25)

    assert result["airport_name"] == "Test Airport"
    assert result["flights"][0]["callsign"] == "AAL123"
    assert result["flights"][0]["latitude"] == 47.6
    assert result["flights"][0]["longitude"] == -122.4
