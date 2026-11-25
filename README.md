# Open Seed

[Browse Open Seed](https://coolcode.ca/openseed/) to find official Linux torrents, openly licensed archive films and downloadable research data with source provenance and dated availability checks.

<!-- coolcode:guide -->
Search Debian and choose Linux to find official installer torrents, or browse Archive media and Research data. “Available” means the small torrent was parsed or the first byte of the selected data file responded at the shown time. It does not mean the whole payload was downloaded or that seeders are currently online. Check the licence and publisher’s checksum before use.
<!-- /coolcode:guide -->

## Sources and interpretation

- Official Ubuntu LTS release folders, Debian current amd64/arm64 torrent directories and the Arch download page. The collector discovers current torrent filenames from these pages; it does not guess versioned download paths. Linux distributions contain individually licensed packages and some installers include separately licensed firmware.
- Internet Archive metadata for configured films. Only explicit public-domain, CC BY or CC BY-SA licence URLs are admitted. The uploader supplies the licence; Open Seed is not a rights clearance service. Torrent payload totals may include multiple encodings and metadata files.
- Zenodo public research records found by configured searches, filtered to open-access datasets with allowlisted licences. The card selects the smallest file from each record for a lightweight entry point, displays its filename/size/checksum, and separately shows the full record's size and file count. The source page provides all files and citations.

This is not a full catalogue or a recommendation to execute software. There are no embedded torrent clients, seeding, magnet auto-launches, invented live seeder counts or unlicensed-media searches. Academic Torrents was investigated but its feed was unavailable from the collection environment; it is not represented as verified data.

## Verification and scheduling

**Browser tool · Check and publish** runs daily at **10:17 UTC** and on manual dispatch. A bounded GET parses each small torrent (maximum 4 MB). A research-file check sends `Range: bytes=0-0`, reads at most one byte and closes the response even if the server ignores Range. Full media, installer and dataset payloads are not downloaded. HTTP failures are published honestly beside the affected item. Source-published checksums are shown where available, with algorithm and filename; no claim is made that the payload itself was verified.

All requests are HTTPS to explicit source-domain families. Redirects are checked against the same allowlist. A source metadata failure preserves the prior complete catalogue and fails the refresh; it cannot publish an empty successful edition. Successful source collection can report unavailable individual downloads. `web/data/catalogue.json` contains `checked_at`, individual check dates, source counts and availability states. Source data is committed only after unit, build and browser checks succeed, before Pages deployment. Publication workflows are serialized and scheduled/manual runs check out current `main`.

The independent watchdog should probe `/openseed/data/catalogue.json`, field **`checked_at`**, with a 72-hour freshness threshold and dispatch `.github/workflows/pages.yml`. The generated weekly `schedule-guard.yml` allowlists that collector and itself; it is not a replacement for freshness monitoring. No API keys are needed.

## Expand or customize

Edit `config/sources.json`:

- Add official distribution index entries using the existing listing adapter. Include a documented licence/redistribution link and checksum filename. Add a separate adapter for a substantially different publisher format; do not silently scrape arbitrary hosts.
- Add another Internet Archive identifier under `archive.ids`. It appears only if its metadata contains an allowlisted open licence and an actual torrent file.
- Change `zenodo.queries`, its search row count and the allowed licence IDs. Dataset filters still apply. `max_items_per_source` bounds collection size, not browser search; accepted range is 1–50.

Run `python3 scripts/refresh.py`, review `web/data/catalogue.json`, run the checks, and push to `main`; alternatively push configuration and manually dispatch **Browser tool · Check and publish**. Adding sources must also update the explicit HTTPS host allowlist where needed, tests and this source note. Ordinary code pushes build offline from the saved catalogue and do not imply a fresh download check.

```sh
node --test tests/*.test.mjs
python3 -m unittest discover -s tests -v
python3 scripts/build.py
```

CI tests the real saved catalogue, combined filters, safe text rendering, project subpaths and mobile layout with Chromium. `dist/` is generated and not committed. The homepage catalogue and watchdog are maintained centrally in `jsdyer/jsdyer.github.io`.

## Privacy

Filtering happens in browser memory and is not saved. Original-source, download and external-search links contact their respective providers only when opened. The external-search links include the search terms. CoolCode's standard aggregate page counter receives the tool ID, not filters. CSV export is local and protects leading spreadsheet formula characters.

## Source documentation

- [Ubuntu official torrents](https://ubuntu.com/download/alternative-downloads) and [verification](https://ubuntu.com/tutorials/how-to-verify-ubuntu)
- [Debian official torrents](https://www.debian.org/CD/torrent-cd/)
- [Arch download and verification](https://archlinux.org/download/)
- [Internet Archive metadata API](https://archive.org/developers/md-read.html)
- [Zenodo developers](https://developers.zenodo.org/) and [licence/data policies](https://about.zenodo.org/policies/)
