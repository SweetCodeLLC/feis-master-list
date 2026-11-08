# feis-master-list

Builds a merged list of upcoming feiseanna from several public sources and commits it
nightly via GitHub Actions. Output (for your app to read from the repo's raw URL):

- `data/feiseanna.json` / `data/feiseanna.csv`: upcoming events, deduped, with every known
  registration link per platform (`registration_links: {quickfeis: ..., feisworx: ...}`).
- `data/undated.json`: items a source listed without a date (held back, not merged).
- `data/sources/<name>.json`: last good snapshot per source (a failing source never wipes data).

## Setup

1. Create a repo, copy these files in, push.
2. Repo **Settings → Secrets and variables → Actions → Variables**: add `FEIS_CONTACT`
   (a URL or e-mail where site owners can reach you). It goes in the User-Agent.
3. **Actions → Update feis master list → Run workflow**. After that it runs daily.
4. Local run: `pip install -r requirements.txt && python -m feis_master.run`; tests: `pytest`.

## Source status

| Source | State | Notes |
|---|---|---|
| IDTANA | **on** | REST API (allowed) enumerates events; each detail page gives date, venue, host, region, registration link. Past events aren't refetched. |
| FeisWorx | **on** | `feisinfo.php` table. Registrant lists ("Who's Registered?") and registrar e-mails are never read or stored. Only shows a rolling window of upcoming events. |
| Western Canada RSS | off | Set `url` in `config/sources.yml`. Feed has no dates, so items go to `undated.json` unless a date is in the title/description. Don't use its iCal/JSON exports (robots disallows). |
| QuickFeis | scaffold | Markup not inspected yet, so no parser. Run the **Probe platform pages** workflow, download the artifact, write `fetch`. Links to QuickFeis already appear via IDTANA registration links. |
| iFeis (ifeis.net) | scaffold | List is JavaScript-rendered: check the probe's URL hints for a JSON endpoint before using a headless browser. |
| FeisWeb | **gated** | Terms forbid reproducing/redistributing without written consent. Adapter refuses to run until you get consent and set `written_consent: true`. Links via IDTANA still work. |
| Planxti | **excluded** | Terms limit use to individual use and forbid republishing/derivative works. Link out; ask them for a feed or permission. |

## Behavior worth knowing

- robots.txt is honored (a disallowed URL is skipped), requests are rate-limited per host,
  and conditional GET (ETag/Last-Modified) is cached between runs.
- Dedupe key: same start date + compatible state + similar normalized name. Registration links
  from all sources are unioned.
- A run that returns under 50% of the previous snapshot is treated as a failure and ignored.
- GitHub-hosted runners use datacenter IPs that some sites block. Don't try to evade blocks;
  contact the site instead.
- Not legal advice. Terms and robots rules change, so re-check them periodically.

## Known limits

- Parsers for IDTANA and FeisWorx were written from the structure of the pages as described
  during research, not from saved raw HTML, and tests use synthetic fixtures. The first real run
  may need small selector tweaks. Save a few real pages into `tests/fixtures/` and extend the tests.
- IDTANA location parsing assumes the stacked layout venue / street / city / state.

## License

Code: GNU AGPL-3.0 (see `LICENSE`). Data: compiled from third-party public listings; rights in the
underlying content remain with the original sources, and it is provided as-is with no warranty.
Each record links back to its source.
