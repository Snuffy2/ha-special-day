# ha-special-day

ha-special-day adds two Home Assistant entities that show whether an occasion
applies today and what it is. It combines its built-in dates with your own
dates and, optionally, all-day events from selected calendars. You can use the
entities in a dashboard or in your own automations.

## Install and set up

Install this integration through [HACS](https://www.hacs.xyz/) (Home Assistant
Community Store). HACS must already be installed and set up in Home Assistant.

1. Open **HACS** from the Home Assistant sidebar.
2. Open the three-dot menu in the top-right corner and select **Custom
   repositories**.
3. Enter `https://github.com/Snuffy2/ha-special-day` as the repository URL.
4. Select **Integration** as the type, then select **Add**.
5. Close the custom repositories window and search HACS for **ha-special-day**.
6. Open its page, select **Download**, and confirm the download in the dialog.
7. Restart Home Assistant.
8. Go to **Settings → Devices & services → Add integration** and search for
   **ha-special-day** to complete setup.

For screenshots of the custom repository steps, see the
[HACS custom repository guide](https://www.hacs.xyz/docs/faq/custom_repositories/).

During setup, leave **Personal rules file** blank to use the built-in dates. To
use your own dates, first create a JSON file inside your Home Assistant config
folder (`/config`), then enter its path relative to that folder. For example,
enter `ha_special_day_rules.json` for `/config/ha_special_day_rules.json`. The
file must already exist. You can also select calendars; only their all-day
events are used.

The integration supports one configuration and creates two entities:

| Entity | What it shows |
| --- | --- |
| `binary_sensor.ha_special_day` | `on` when one or more occasions apply today; otherwise `off` |
| `sensor.ha_special_day_description` | A readable list of today's occasions |

Home Assistant may choose different entity IDs if these names are already in
use. Both entities have these attributes:

- `events`: the full list of occasion names.
- `description`: the full text, even if it is longer than 255 characters.
- `last_checked`: when the integration last checked the date and calendars.
- `calendar_errors`: calendar entity IDs that could not be read on the latest
  check.

The sensor's displayed state is limited to 255 characters, but the full text
remains in its `description` attribute. The integration checks at setup, local
midnight, and every 15 minutes. You do not need a helper or a daily automation
just to keep the entities current.

## Add your own dates

Create a JSON file such as `/config/ha_special_day_rules.json`:

```json
{
  "include_defaults": true,
  "rules": {
    "Our anniversary": "7/14",
    "Pancake Day": "Easter-47d",
    "Thanksgiving": "11/1+4@thu",
    "Black Friday": "Thanksgiving+1d"
  },
  "exclude": ["Blue Monday"],
  "bank_holidays": true,
  "seasonal_fallbacks": true
}
```

Choose the file during setup, or change it later from the integration's
**Configure** screen. Keep personal files outside
`custom_components/ha_special_day` so an integration update will not overwrite
them.

The settings are:

| Setting | What it does |
| --- | --- |
| `include_defaults` | Include the built-in date rules. Defaults to `true`. Set to `false` to omit them. |
| `rules` | Add dates or replace built-in dates by using the exact same name. Defaults to an empty object. |
| `exclude` | Hide occasions by exact name, including calculated bank holidays and seasonal labels. Defaults to an empty list. An excluded date can still be used as the basis for another rule. |
| `bank_holidays` | Calculate substitute days for New Year's Day, Christmas Day, and Boxing Day when they fall on a weekend. Defaults to `true`. |
| `seasonal_fallbacks` | Show a day-of-Lent or day-of-Advent label when no other occasion applies. Defaults to `true`. |

To use only your personal date rules,
set `include_defaults`, `bank_holidays`, and `seasonal_fallbacks` to `false`.
Selected calendar events will still be included.

The built-in list contains UK-oriented holidays, Easter dates, and meteor
shower dates. The bank holiday calculation covers the substitute days listed
above; it is not an authoritative source for every public holiday or one-off
change. Use a personal rule or calendar event for an exceptional date.

### Date expressions

An expression starts with a date in **month/day** order (`M/D`), `Easter`, or
the exact name of another rule. Fixed dates repeat each year. A `2/29` date
applies only in leap years. You can add offsets to a date, or combine them to
describe a moving occasion:

| Expression | Meaning |
| --- | --- |
| `12/25` | December 25 each year |
| `Easter-47d` | 47 days before Gregorian Easter Sunday |
| `5/6+2w` | Two weeks after May 6 |
| `1/31+1m` | One calendar month after January 31, using the last day of February |
| `5/1+1@mon` | The first Monday on or after May 1 |
| `3/31-1@sun` | The closest Sunday on or before March 31 |
| `11/1+4@thu+1d` | One day after the fourth Thursday on or after November 1 |
| `Thanksgiving+1d` | One day after the rule named Thanksgiving |

Complete, valid fixed-date and Easter expressions take precedence over rule
names. For example, `7/14+1d` always means July 15, even if a rule has that
name. These literal-shaped names are reserved when used in expressions; use a
distinct name to reference such a rule. Names with extra text, such as
`7/14 anniversary` or `Easter+1d event`, can still be referenced with offsets.

Use `d` for days, `w` for weeks, and `m` for calendar months. Weekday names
are `mon`, `tue`, `wed`, `thu`, `fri`, `sat`, and `sun`; they are not case
sensitive. A weekday offset includes the starting date, so `+1@mon` returns
the same date when it is already Monday. Add another offset to move beyond
that date.

There is also a week-based weekday form for cases where you mean a weekday in
a particular calendar week of the month. For example, `+3w@mon` means the
Monday in the third Monday-to-Sunday week that contains a day of the base
date's month. Week one is the Monday-to-Sunday week containing the month's
first day. `-1w@mon` means the last Monday in that month. For the third Monday
on or after a date, use `+3@mon` instead.

Day or month offsets cannot be combined with a weekday in the same offset. You
can chain offsets, as in `11/1+4@thu+1d`. Named references cannot form a loop.
For very long expressions, the total estimated movement through a chain of
rules is limited to 3,660 days; each month counts as 31 days for that check.

### Apply changes to your rules

Editing the JSON file alone does not apply the changes. In Home Assistant, run
**Developer tools → Actions → ha-special-day: Reload rules** (action ID
`ha_special_day.reload_rules`). A valid file is checked, today's results are
recalculated, and both entities are updated.

If the file cannot be read or contains invalid JSON or date rules, the action
reports an error and keeps the previous working rules and entity state. The
automatic refreshes continue using those working rules. Fix the file before
restarting Home Assistant: at startup the integration reads the file again,
and it cannot set up with an invalid rules file.

## Use calendar events

Selected calendars add all-day events that overlap today, including events
that last more than one day. The start date counts and the end date does not:
an event with start `2026-07-01` and end `2026-07-03` applies on July 1 and 2,
but not July 3. Timed appointments are ignored. Date rules and calendar events
are combined. An occasion appears once when its names match exactly. A
calendar event also replaces the generic Lent or Advent label for that day.

Calendar changes appear within 15 minutes, or sooner if you run **Reload
rules**. If a calendar is unavailable or takes more than 30 seconds to respond,
the integration still shows occasions from its rules. It logs the calendar
problem, lists the calendar in `calendar_errors`, and tries again on the next
refresh. Calendar events are not cached between checks, so a failed calendar
read does not keep events from its previous successful check.

For example, you can make a Home Assistant automation that runs at 08:00,
checks that `binary_sensor.ha_special_day` is `on`, and uses the
`description` attribute of `sensor.ha_special_day_description` in an
announcement. The sensor is already current at midnight; it does not announce
anything by itself. If an automation has several triggers, use a date helper
in that automation if you want to limit it to one announcement per day.

## Contributing

You can report a date correction, a confusing instruction, or a problem
without writing code or installing development tools. See
[CONTRIBUTING.md](CONTRIBUTING.md) for ways to help and for setup and testing
instructions for code changes.

## Attribution

This integration originated from [the Special Day project by
philmale](https://github.com/philmale/special-day). Special thanks to its
author and contributors for the original script, holiday rules, and date
calculations that this integration builds on.
