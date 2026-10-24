# Special Day

A small Home Assistant custom integration that calculates today's occasions and
creates its own entities. Personal holiday rules live in a separate JSON file so
integration updates do not overwrite your changes.

## Install

Requires Home Assistant **2026.10 or newer** (Python 3.14.2 or newer).

1. Copy `custom_components/special_day` into your Home Assistant
   `/config/custom_components/` folder.
2. Restart Home Assistant to discover the integration.
3. Open **Settings → Devices & services → Add integration → Special Day**.
4. Leave the rules file blank for the bundled defaults, or enter the path of an
   existing personal JSON file relative to `/config`. Optionally select calendars.

The integration supports one configuration and creates:

| Entity | Purpose |
| --- | --- |
| `binary_sensor.special_day` | On when at least one occasion applies today |
| `sensor.special_day_description` | Text suitable for “today is …” |

Entity IDs can differ if those names are already taken. Both entities expose
`events` (the complete list), `description` (the full text), `last_checked`
(a timestamp), and `calendar_errors` (calendar entity IDs that could not be read).
The description state is limited to 255 characters; its attributes retain the
complete text.

Status refreshes at setup, local midnight, every 15 minutes, and when rules are
reloaded. No helpers or daily script automation are required.

## Personal rules

Create `/config/special_day_rules.json`, for example:

```json
{
  "include_defaults": true,
  "rules": {
    "Our anniversary": "14/7",
    "Pancake Day": "Easter-47d",
    "Thanksgiving": "1/11+4@thu",
    "Black Friday": "Thanksgiving+1d"
  },
  "exclude": ["Blue Monday"],
  "bank_holidays": true,
  "seasonal_fallbacks": true
}
```

Choose `special_day_rules.json` during setup or through the integration's
**Configure** screen. Files must be inside the Home Assistant config folder;
keep them outside `custom_components/special_day` so updates preserve them.

`rules` adds occasions or replaces a bundled expression by exact name.
`exclude` hides names, including calculated bank holidays or seasonal fallback
names. Excluded rules remain usable as date references. `include_defaults: false`
starts with an empty date-rule list. The `bank_holidays` and `seasonal_fallbacks`
switches separately control the calculated UK substitute holidays and Lent/Advent
fallback descriptions; set both to `false` for a wholly personal calendar.
All three switches default to `true`, and `rules` and `exclude` default to empty.
Unknown settings and malformed entries are rejected.

After editing the file, run **Developer tools → Actions → Special Day: Reload
rules** (`special_day.reload_rules`). It validates the whole file, recalculates
today, and updates both entities. An invalid file produces an error identifying
the problem and leaves the previous working rules and state intact. Automatic
refresh continues using those working rules. The file must be corrected before
restarting Home Assistant, because only the on-disk configuration survives a
restart. Editing the file alone does not reload it.

### Date expressions

Use a base date (`D/M`), `Easter` (Gregorian Easter Sunday), or another rule's exact
name, followed by optional offsets. Fixed dates recur annually. A February 29 rule
is skipped in non-leap years. Named references cannot be circular. Total offsets along a reference chain are
limited to a conservative 3,660-day bound (months count as 31 days for this check).

| Expression | Meaning |
| --- | --- |
| `25/12` | December 25 |
| `Easter-47d` | 47 days before Easter |
| `6/5+2w` | Two weeks after May 6 |
| `31/1+1m` | One calendar month later, clamped to the last day of February |
| `1/5+1@mon` | First Monday on or after May 1 |
| `31/3-1@sun` | Last Sunday on or before March 31 |
| `1/11+4@thu+1d` | Friday following the fourth Thursday of November |
| `Thanksgiving+1d` | One day after the rule named Thanksgiving |

Weekday names are `mon`, `tue`, `wed`, `thu`, `fri`, `sat`, `sun` (case insensitive).
Weekday occurrences are inclusive: `+1@mon` returns the base date if it is Monday.
For compatibility with the original script, `+3w@mon` means Monday in the third
calendar week of the base month, where week one contains the first of the month
and starts on Monday. `-1w@mon` means the last Monday in the base month. Prefer
`+3@mon` for the third Monday on or after a specific date. Day and month offsets
cannot be combined directly with `@weekday`; chain separate offsets instead.

The bundled list retains the original script's UK-oriented holidays, meteor
shower dates, Easter-related days, substitute bank holidays, and Lent/Advent
fallbacks. Black Friday now follows Thanksgiving, including years when it falls
on the fifth Friday in November. Month offsets are implemented. These are annual
rules, not an authoritative feed of exceptional public-holiday changes; use
personal overrides or calendar events for one-off occasions.

## Calendars and announcements

Selected calendars contribute **all-day events** overlapping today, including
multi-day events; an event's end date is exclusive. All matching events are read,
merged with calculated occasions, and deduplicated by exact name. Timed
appointments are ignored. A calendar occasion suppresses the generic Lent/Advent
fallback, just as a named holiday does. Changes to calendar events appear within
15 minutes, or immediately when you run Reload rules.

If a calendar is unavailable or times out, local rules still work. The integration
logs a warning and lists the failed calendar in `calendar_errors`; it retries on
the next refresh. Calendar events are not cached through failures.

Keep announcements and lighting in separate automations. For example, create a
UI automation with a daily **Time** trigger at 08:00, a **State** condition that
`binary_sensor.special_day` is `on`, and your announcement action using the
sensor's `description` attribute. Status is already current at midnight; checking
it never announces anything. If you need only one announcement per day across
multiple triggers, manage that in the announcement automation with a date helper.

## Migrating from the script

The original [special_day.yaml](special_day.yaml) remains available as a legacy
script. It is independent of this integration and requires all three helpers:
`input_boolean.special_day`, `input_text.special_day_text`, and
`input_datetime.special_day_last_checked`.

To migrate:

1. Move personal name/date entries from the script's `special_days` dictionary to
   the JSON file's `rules` object. Use `exclude` for bundled names you removed.
2. Set up the integration and verify its entities and occasions.
3. Update automations, scripts, and dashboards from `input_boolean.special_day`
   to the new binary sensor, and from `input_text.special_day_text` to the new
   description sensor (or its full `description` attribute).
4. Remove calls to `script.check_for_special_day` from announcement and lighting
   automations. Schedule those actions independently.
5. Disable the old daily check automation and remove its helpers only after
   checking that no other automations reference them.

The old last-checked helper controlled script/announcement execution. The new
`last_checked` attribute is informational; it does not deduplicate announcements.
The integration does not import or rename existing helpers automatically.

## Development

```sh
uv sync
./.venv/bin/pytest -q
./.venv/bin/ruff check .
./.venv/bin/ruff format --check .
./.venv/bin/mypy
./.venv/bin/prek run --all-files
```

The tests load the real Home Assistant integration and entity platforms and cover
configuration, rule reload rollback, midnight updates, calendars, and unload, as
well as the pure date evaluator. `uv.lock` pins the validation environment.
