# WS02 — Menu

**Goal:** the menu the tablets read, the 86 switch that removes an item from every device instantly,
and the price edit that is logged when it happens during service.

**Depends on:** WS00. **Blocks:** WS03 (item snapshots), WS07 (ordering UI).

## Owns

`backend/apps/menu/`.

## Endpoints

`GET /menu` (staff + guest, ETag) · `POST /menu/items/{id}/86` · `POST /menu/items/{id}/restore` ·
`POST /menu/items/{id}/price` (authorisation required during service hours).

## Events

`ITEM_86ED` `ITEM_RESTORED` `PRICE_CHANGED` (aggregate `MENU_ITEM`).

## Build

1. Django admin for categories, items (image upload to `MEDIA_ROOT` now; object storage is WS13),
   modifier groups, modifiers, and the item↔group link with ordering. Inline modifiers on the group.
   Soft delete only: `is_active`.
2. `GET /menu` serializer: categories (active, sorted) → items (active, sorted, with `is_available`,
   `prep_station`, `price_pesewas`) → modifier groups (`selection`, `is_required`) → modifiers
   (`price_pesewas`, `is_default`, `is_available`). ETag = sha256 of the serialized body; `If-None-Match` → 304.
   Cache the body in Redis per restaurant; invalidate on any menu write (admin save signal or command).
3. 86 / restore as commands; the projector flips `is_available`. Publish so every device drops the item
   without a menu refetch (payload carries `menu_item_id`, `name`, `is_available`).
4. Price change as a command. "Service hours" = `Restaurant.service_start`/`service_end` (add the two
   `TimeField`s + migration); inside them the view sets `requires_authorisation=True` with purpose
   `PRICE_CHANGE_IN_SERVICE`. Payload carries `old_price_pesewas`, `new_price_pesewas`.
5. `menu/snapshot.py::snapshot_line(menu_item, modifier_ids, quantity)` → `(name, unit_price, prep_station,
   modifiers[{id, name, price_pesewas}], line_total)`. Validates: item active and available; each modifier
   belongs to a group linked to the item and is available; `ONE` groups have at most one; `is_required`
   groups have exactly one. Raises `ApiError` with the codes in `09-api-contract.md §2`. **WS03 calls this;
   it is the only place a price is read from the menu.**

## Tests required

- ETag 304 round trip; menu write invalidates.
- 86 → `is_available=false` in projection and in the next `GET /menu`; event published.
- `snapshot_line` property tests: `line_total == (unit + Σ paid modifiers) × qty`; required-group missing → 422;
  `ONE` group with two → 422; unavailable modifier → 422.
- Price change inside service hours without authorisation → 403; with → `PRICE_CHANGED` carrying both prices.

## Exit criteria

Seeded RENZY menu (from `seed_renzy`) renders through `GET /menu`; kitchen can 86 the guinea fowl and a
second client sees it disappear on the stream.
