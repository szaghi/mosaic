"""Tests for mosaic.parsing — DOI normalisation and secret redaction."""

import pytest

from mosaic.parsing import normalise_doi, redact_secrets


class TestNormaliseDoi:
    @pytest.mark.parametrize(
        "raw",
        [
            "10.1234/foo",
            "https://doi.org/10.1234/foo",
            "http://doi.org/10.1234/foo",
            "https://dx.doi.org/10.1234/foo",
            "http://dx.doi.org/10.1234/foo",
            "https://www.doi.org/10.1234/foo",
            "HTTPS://DOI.ORG/10.1234/foo",
            "doi:10.1234/foo",
            "DOI: 10.1234/foo",
            "  10.1234/foo  ",
        ],
    )
    def test_prefixes_stripped(self, raw):
        assert normalise_doi(raw) == "10.1234/foo"

    def test_percent_encoded_url_form_decoded(self):
        assert normalise_doi("https://doi.org/10.1234%2Ffoo") == "10.1234/foo"

    def test_bare_doi_not_decoded(self):
        # A bare DOI may legitimately contain "%"; only URL forms are decoded.
        assert normalise_doi("10.1234/50%25off") == "10.1234/50%25off"

    def test_case_of_suffix_preserved(self):
        assert normalise_doi("https://doi.org/10.1234/ABC") == "10.1234/ABC"

    @pytest.mark.parametrize("raw", [None, "", "   ", "doi:", "https://doi.org/"])
    def test_empty_returns_none(self, raw):
        assert normalise_doi(raw) is None


class TestRedactSecrets:
    @pytest.mark.parametrize(
        "param", ["apikey", "api_key", "api-key", "access_token", "token", "inst_token", "key"]
    )
    def test_credential_params_masked(self, param):
        msg = f"Client error '403' for url 'https://api.example.org/s?q=x&{param}=SECRET123&n=5'"
        out = redact_secrets(msg)
        assert "SECRET123" not in out
        assert f"{param}=***" in out
        assert "q=x" in out and "n=5" in out

    def test_first_query_param_masked(self):
        assert redact_secrets("https://x.org/a?apikey=S3CR3T") == "https://x.org/a?apikey=***"

    def test_email_masked(self):
        out = redact_secrets("url 'https://api.crossref.org/works?query=a&mailto=me@uni.edu'")
        assert "me@uni.edu" not in out

    def test_unrelated_params_untouched(self):
        msg = "https://x.org/s?query=monkey&keyword=deep"
        assert redact_secrets(msg) == msg

    def test_plain_text_untouched(self):
        assert redact_secrets("Connection refused") == "Connection refused"
