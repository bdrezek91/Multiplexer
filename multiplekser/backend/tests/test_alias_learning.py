from app.modules.documents import repository as doc_repo
from app.modules.documents.models import DocumentItemModel
from app.modules.matcher import match_against_catalog
from app.modules.products import Catalog
from app.modules.products.models import ProductAliasSuggestionModel
from scripts.import_catalog import import_catalog


def _document_with_item(db_session, admin_user, *, name: str):
    document = doc_repo.create_document(
        db_session,
        user_id=admin_user.id,
        file_key="documents/alias-learning/test.jpg",
        mime="image/jpeg",
        original_filename="test.jpg",
    )
    document.status = "done"
    document.dzial = "elektryka"
    item = DocumentItemModel(
        document_id=document.id,
        sequence=0,
        rozpoznana_nazwa=name,
        matched_product_id=None,
        match_kod=None,
        match_nazwa=None,
        match_jm=None,
        ilosc_wydana=1.0,
        ilosc_zuzyta=None,
        ilosc_finalna=1.0,
        match_quality="bad",
        match_score=0.0,
        off_form=True,
        needs_review=True,
        form_note="",
        uwagi="",
        confidence=40.0,
        ilosc_z_dodatkowej_kontroli=False,
    )
    db_session.add(item)
    db_session.commit()
    db_session.refresh(item)
    return document, item


def test_reczna_korekta_tworzy_pending_a_approve_uczy_matchera_i_przezywa_import(
    client, admin_headers, admin_user, db_session, baza_elektryka_json,
):
    import_catalog(db_session, baza_elektryka_json)
    document, item = _document_with_item(db_session, admin_user, name="wtyk RJ45")

    response = client.patch(
        f"/documents/{document.id}/items/{item.id}",
        json={"match_kod": "KORYTKO 32X15"},
        headers=admin_headers,
    )
    assert response.status_code == 200, response.text

    pending = (
        db_session.query(ProductAliasSuggestionModel)
        .filter(ProductAliasSuggestionModel.status == "pending")
        .one()
    )
    assert pending.alias_text == "wtyk RJ45"
    assert pending.target_kod == "KORYTKO 32X15"
    assert pending.source_document_id == document.id
    assert pending.source_item_id == item.id

    listed = client.get(
        "/products/knowledge/suggestions",
        params={"status": "pending", "dzial": "elektryka"},
        headers=admin_headers,
    )
    assert listed.status_code == 200, listed.text
    assert len(listed.json()) == 1

    approved = client.post(
        f"/products/knowledge/suggestions/{pending.id}/approve",
        headers=admin_headers,
    )
    assert approved.status_code == 200, approved.text
    assert approved.json()["status"] == "approved"

    # Import bazowego katalogu kasuje product_alias, ale NIE warstwe wiedzy DAMPOL.
    import_catalog(db_session, baza_elektryka_json)

    catalog = Catalog.from_db(db_session, dzial="elektryka")
    product = catalog.find_by_kod("KORYTKO 32X15")
    assert product is not None
    assert "wtyk RJ45" in [alias.text for alias in product.aliasy]

    match = match_against_catalog("wtyk RJ45", catalog)
    assert match.kod == "KORYTKO 32X15"


def test_zmiana_samej_ilosci_nie_tworzy_propozycji_aliasu(
    client, admin_headers, admin_user, db_session, baza_elektryka_json,
):
    import_catalog(db_session, baza_elektryka_json)
    document, item = _document_with_item(db_session, admin_user, name="wtyk RJ45")

    response = client.patch(
        f"/documents/{document.id}/items/{item.id}",
        json={"ilosc_finalna": 2},
        headers=admin_headers,
    )
    assert response.status_code == 200, response.text
    assert db_session.query(ProductAliasSuggestionModel).count() == 0


def test_odrzucona_propozycja_nie_wchodzi_do_katalogu(
    client, admin_headers, admin_user, db_session, baza_elektryka_json,
):
    import_catalog(db_session, baza_elektryka_json)
    document, item = _document_with_item(db_session, admin_user, name="papierowa nazwa xyz")

    response = client.patch(
        f"/documents/{document.id}/items/{item.id}",
        json={"match_kod": "KORYTKO 32X15"},
        headers=admin_headers,
    )
    assert response.status_code == 200
    pending = db_session.query(ProductAliasSuggestionModel).one()

    rejected = client.post(
        f"/products/knowledge/suggestions/{pending.id}/reject",
        headers=admin_headers,
    )
    assert rejected.status_code == 200
    assert rejected.json()["status"] == "rejected"

    catalog = Catalog.from_db(db_session, dzial="elektryka")
    product = catalog.find_by_kod("KORYTKO 32X15")
    assert product is not None
    assert "papierowa nazwa xyz" not in [alias.text for alias in product.aliasy]
