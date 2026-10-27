"""Run from frontend: python -m unittest discover -s test -p test_county_age_breakdown.py."""

import json
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

import dash
import dash_bootstrap_components as dbc

import app  # noqa: F401 - Register pages before importing callbacks.
from county_data import county_metrics
from pages import home
from test.test_disease_parameters import components


def output_county():
    values = {'S': 100, 'E': 10, 'IA': 2, 'IP': 3, 'IS': 5, 'H': 7, 'R': 20, 'D': 1}
    return {
        'fips_id': '48201',
        'compartment_summary': {key: value * 60 for key, value in values.items()},
        'compartment_subgroups': {
            key: {
                risk: {vax: [value * (age + 1) for age in range(5)] for vax in ('U', 'V')}
                for risk in ('L', 'H')
            }
            for key, value in values.items()
        },
    }


class CountyAgeBreakdownTests(unittest.TestCase):
    def test_sums_risk_and_vaccination_counts_without_double_counting(self):
        county = county_metrics(output_county())
        self.assertEqual(county['ageGroups'][0]['infected'], 40)
        self.assertEqual(county['ageGroups'][0]['deceased'], 4)
        self.assertEqual(sum(age['infected'] for age in county['ageGroups']), county['infected'])
        self.assertEqual(sum(age['deceased'] for age in county['ageGroups']), county['deceased'])
        self.assertAlmostEqual(county['ageGroups'][0]['infectedPercent'], 10 / 148 * 100)
        self.assertAlmostEqual(county['ageGroups'][4]['deceasedPercent'], 1 / 148 * 100)

    def test_legacy_models_and_zero_population(self):
        legacy_infectious = county_metrics({'compartment_summary': {
            'S': 80, 'A': 3, 'I': 4, 'T': 5, 'R': 8,
        }})
        self.assertEqual(legacy_infectious['infected'], 12)
        self.assertEqual(legacy_infectious['infectedPercent'], 12)
        county = output_county()
        for section in ('compartment_summary', 'compartment_subgroups'):
            county[section] = {key: val for key, val in county[section].items() if key in ('S', 'E', 'R')}
        legacy = county_metrics(county)
        self.assertEqual(legacy['deceased'], 1200)
        self.assertEqual(legacy['ageGroups'][0]['deceased'], 80)
        empty = county_metrics({
            'compartment_subgroups': {'S': {'L': {'U': [0] * 5}}},
        })
        self.assertEqual(empty['ageGroups'][0]['infectedPercent'], 0)
        self.assertEqual(empty['ageGroups'][0]['deceasedPercent'], 0)

    def test_missing_and_incomplete_subgroups_are_unavailable(self):
        self.assertIsNone(county_metrics({})['ageGroups'])
        county = output_county()
        county['compartment_subgroups']['S']['L']['U'] = [1, 2]
        self.assertIsNone(county_metrics(county)['ageGroups'])

#     def table(self, events=None, **kwargs):
#         options = dict(
#             event_data=events or [{'counties': [county_metrics(output_county())]}],
#             timeline_value=0, view_type='count',
#             location_assets={'mapping': {'Harris': '48201'}},
#             search_text='', sort_state=None, selected_county='48201',
#             selected_model='seihrd-stochastic', expanded_counties=['48201'],
#         )
#         options.update(kwargs)
#         return home.update_table(**options)[0]

#     def test_expanded_table_accessibility_and_age_values(self):
#         table = self.table()
#         all_components = list(components(table))
#         collapse = next(c for c in all_components if isinstance(c, dbc.Collapse))
#         self.assertTrue(collapse.is_open)
#         button = next(c for c in all_components if getattr(c, 'id', None) == {
#             'type': 'county-age-toggle', 'fips': '48201',
#         })
#         self.assertEqual(getattr(button, 'aria-expanded'), 'true')
#         self.assertEqual(json.loads(getattr(button, 'aria-controls')), collapse.id)
#         self.assertTrue(any('Loading age breakdown' in str(getattr(c, 'children', '')) for c in all_components))

#     def test_percent_mode_and_expansion_survive_day_search_and_sort_changes(self):
#         county = county_metrics(output_county())
#         events = [{'counties': [county]}, {'counties': [county]}]
#         table = self.table(
#             events, timeline_value=1, view_type='percent', search_text='Harris',
#             sort_state={'col': 'name', 'dir': 'asc'},
#         )
#         self.assertTrue(next(c for c in components(table) if isinstance(c, dbc.Collapse)).is_open)
#         closed = self.table(expanded_counties=[])
#         self.assertFalse(next(c for c in components(closed) if isinstance(c, dbc.Collapse)).is_open)

    def test_fetch_retains_age_metrics(self):
        output = output_county()
        response = Mock(status_code=200, text='OK')
        response.json.return_value = {'day': 0, 'total_summary': output['compartment_summary'], 'data': [output]}
        with patch.object(home.requests, 'get', return_value=response):
            events, _, _, ages = home.fetch_simulation_data(1, {'isRunning': True}, [])
        day = events.to_plotly_json()['operations'][0]['params']['value']
        age_day = ages.to_plotly_json()['operations'][0]['params']['value']
        self.assertNotIn('ageGroups', day['counties'][0])
        self.assertEqual(age_day['48201'][0]['infected'], 40)

#     def test_table_contains_only_placeholders_even_for_expanded_county(self):
#         counties = [{**county_metrics(output_county()), 'fips': str(48001 + 2 * i)} for i in range(254)]
#         table = self.table([{'counties': counties}], expanded_counties=['48001', '48003'])
#         rendered = list(components(table))
#         self.assertEqual(sum(isinstance(c, dbc.Collapse) and c.is_open for c in rendered), 1)
#         self.assertFalse(any(getattr(c, 'className', '') == 'county-age-table mb-0' for c in rendered))

    def test_idle_poll_does_not_republish_history_or_trigger_rendering(self):
        events = [{'counties': []}]
        self.assertEqual(home.fetch_simulation_data(1, {'isRunning': False}, events), (dash.no_update,) * 4)
        response = Mock(status_code=404, text='not calculated')
        with patch.object(home.requests, 'get', return_value=response):
            self.assertEqual(home.fetch_simulation_data(1, {'isRunning': True}, events), (dash.no_update,) * 4)

#     def test_rerendered_buttons_do_not_trigger_another_table_update(self):
#         for kind, handler, state in (
#             ('sort-btn', home.handle_sort_click, {'col': 'infected', 'dir': 'desc'}),
#             ('county-row', home.handle_county_row_click, '48201'),
#         ):
#             with patch.object(home, 'ctx', SimpleNamespace(
#                 triggered_id={'type': kind, 'fips': '48201', 'col': 'infected'},
#                 triggered=[{'value': 0}],
#             )):
#                 self.assertIs(handler([0], state), dash.no_update)

#     def test_registered_table_callback_accepts_expansion_and_model_state(self):
#         client = app.app.server.test_client()
#         self.assertEqual(client.get('/_dash-layout').status_code, 200)
#         key = next(key for key in app.app.callback_map if 'spread-table.children' in key)
#         callback = app.app.callback_map[key]
#         values = {
#             'county-table-day': {
#                 'counties': [county_metrics(output_county())],
#                 'mapping': {'Harris': '48201'}, 'expanded': ['48201'],
#             },
#             'view-toggle': 'percent',
#             'location-assets-store': {'mapping': {'Harris': '48201'}},
#             'county-search': '',
#             'county-table-sort': {'col': 'infected', 'dir': 'desc'},
#             'selected-county-store': None,
#             'expanded-counties': ['48201'],
#             'selected-model-store': 'seihrd-stochastic',
#         }
#         response = client.post('/_dash-update-component', json={
#             'output': key,
#             'outputs': [
#                 {'id': 'spread-table', 'property': 'children'},
#                 {'id': 'county-controls', 'property': 'style'},
#             ],
#             'inputs': [{**item, 'value': values[item['id']]} for item in callback['inputs']],
#             'state': [{**item, 'value': values[item['id']]} for item in callback['state']],
#             'changedPropIds': ['county-table-day.data'],
#         })
#         self.assertEqual(response.status_code, 200, response.data)
#         self.assertIn(b'"is_open":true', response.data)
#         self.assertIn(b'Loading age breakdown', response.data)
#         self.assertNotIn('expanded-counties', [item['id'] for item in callback['inputs']])
#         self.assertIn('expanded-counties', [item['id'] for item in callback['state']])

#     def test_expansion_timestamp_state_is_present_in_the_real_layout(self):
#         stores = {getattr(c, 'id', None): c for c in components(home.layout())
#                   if isinstance(getattr(c, 'id', None), str)}
#         self.assertEqual(stores['county-age-click-state'].data, {'state': None, 'timestamp': -1})
#         toggles = [c for c in components(self.table())
#                    if isinstance(getattr(c, 'id', None), dict)
#                    and c.id.get('type') == 'county-age-toggle']
#         self.assertEqual(toggles[0].n_clicks_timestamp, -1)
#         client = app.app.server.test_client()
#         dependencies = client.get('/_dash-dependencies').get_json()
#         expansion = next(item for item in dependencies
#                          if (item.get('clientside_function') or {}).get('function_name') == 'updateRow')
#         self.assertEqual(expansion['inputs'][0]['property'], 'n_clicks_timestamp')
#         self.assertIn('county-age-click-state', [item['id'] for item in expansion['state']])


if __name__ == '__main__':
    unittest.main()
