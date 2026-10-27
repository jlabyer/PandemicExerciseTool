"""Community grid and detail panel checks; no browser or simulation required."""

import json
import unittest
from types import SimpleNamespace
from unittest.mock import patch

import dash
import dash_ag_grid as dag

import app
from county_data import county_metrics
from county_grid import age_panel, create_county_grid_panel, grid_columns, grid_rows
from pages import home
from test.test_county_age_breakdown import output_county
from test.test_disease_parameters import components


class CountyGridTests(unittest.TestCase):
    def setUp(self):
        self.county = county_metrics(output_county())
        self.day = {'day': 0, 'counties': [self.county], 'mapping': {'Harris': '48201'}}
        self.request = {'fips': '48201', 'day': 0, 'pending': False, 'ages': self.county['ageGroups']}
        self.selected = [{'fips': '48201', 'name': 'Harris', 'infected': 600, 'outcome': 60}]

    def test_layout_uses_community_grid_and_separate_detail_panel(self):
        panel = list(components(create_county_grid_panel()))
        grid = next(c for c in panel if isinstance(c, dag.AgGrid))
        self.assertFalse(grid.enableEnterpriseModules)
        self.assertEqual(grid.getRowId, 'params.data.fips')
        self.assertEqual(grid.dashGridOptions['rowSelection']['mode'], 'singleRow')
        self.assertNotIn('masterDetail', grid.dashGridOptions)
        self.assertNotIn('autoHeight', grid.dashGridOptions)
        ids = [getattr(c, 'id', None) for c in panel]
        self.assertIn('county-age-body', ids)
        self.assertNotIn('expanded-counties', ids)
        self.assertFalse(any(isinstance(value, dict) for value in ids))

    def test_grid_rows_use_numeric_values_and_exclude_age_history(self):
        self.assertEqual(grid_rows(self.day, 'count'), self.selected)
        percent = grid_rows(self.day, 'percent')[0]
        self.assertAlmostEqual(percent['infected'], 10 / 148 * 100)
        self.assertAlmostEqual(percent['outcome'], 1 / 148 * 100)
        self.assertNotIn('ageGroups', percent)
        zero_padded = grid_rows({'counties': [{'fips': '1001'}], 'mapping': {'Autauga': '01001'}}, 'count')[0]
        self.assertEqual(zero_padded['fips'], '01001')
        self.assertEqual(zero_padded['name'], 'Autauga')

    def test_empty_data_and_model_headers(self):
        rows, columns, style = home.update_county_grid(None, 'count', 'seirs-deterministic')
        self.assertEqual(rows, [])
        self.assertEqual(style, {'display': 'none'})
        self.assertEqual(columns[2]['headerName'], 'Recovered')
        self.assertEqual(grid_columns('percent', 'seihrd-stochastic')[2]['headerName'], 'Deceased')
        self.assertNotIn('sort', columns[1])
        self.assertEqual(columns[1]['initialSort'], 'desc')

    def test_selection_links_to_map_and_clears_on_jurisdiction_change(self):
        with patch.object(home, 'ctx', SimpleNamespace(triggered_id='county-grid')):
            self.assertEqual(home.select_grid_county(self.selected, 'Texas', None), '48201')
            self.assertIs(home.select_grid_county(self.selected, 'Texas', '48201'), dash.no_update)
            self.assertIsNone(home.select_grid_county([], 'Texas', '48201'))
        with patch.object(home, 'ctx', SimpleNamespace(triggered_id='selected-state-store')):
            self.assertIsNone(home.select_grid_county(self.selected, 'Delaware', '48201'))
        self.assertEqual(home.clear_grid_selection('Delaware'), [])

    def test_detail_panel_has_five_age_groups_and_follows_count_percentage_mode(self):
        for view, expected in [('count', ['0-4 years', '40', '4']), ('percent', ['0-4 years', '6.8%', '0.7%'])]:
            title, body = age_panel('48201', self.request, view, 'seihrd-stochastic', self.selected)
            self.assertEqual(title, 'Harris — age breakdown')
            table = body.children[-1]
            rows = table.children[1].children
            self.assertEqual(len(rows), 5)
            self.assertEqual([cell.children for cell in rows[0].children], expected)
            self.assertEqual(table.children[0].children.children[2].children, 'Deceased')
        _, body = age_panel('48201', self.request, 'count', 'seirs-stochastic', self.selected)
        self.assertEqual(body.children[-1].children[0].children.children[2].children, 'Recovered')

    def test_details_handle_no_selection_pending_unavailable_and_stale_county(self):
        _, body = age_panel(None, self.request, 'count', '', [])
        self.assertIn('Select a county', body.children)
        for request in (None, {**self.request, 'pending': True}, {**self.request, 'fips': '48001'}):
            _, body = age_panel('48201', request, 'count', '', self.selected)
            self.assertIn('Loading', body.children)
        _, body = age_panel('48201', {**self.request, 'ages': None}, 'count', '', self.selected)
        self.assertIn('unavailable', body.children)

    # Restore with the optional cross-column search field and callback.
    # def test_search_changes_only_grid_quick_filter(self):
    #     operations = home.filter_county_grid('Harris').to_plotly_json()['operations']
    #     self.assertEqual(operations, [{'operation': 'Assign', 'location': ['quickFilterText'], 'params': {'value': 'Harris'}}])

    def call_callback(self, output_token, values, changed):
        client = app.app.server.test_client()
        self.assertEqual(client.get('/_dash-layout').status_code, 200)
        key = next(key for key in app.app.callback_map if output_token in key)
        callback = app.app.callback_map[key]
        outputs = callback['output']
        output_list = outputs if isinstance(outputs, list) else [outputs]
        output_spec = [{'id': out.component_id, 'property': out.component_property} for out in output_list]
        response = client.post('/_dash-update-component', json={
            'output': key, 'outputs': output_spec if isinstance(outputs, list) else output_spec[0],
            'inputs': [{**item, 'value': values[item['id']]} for item in callback['inputs']],
            'state': [{**item, 'value': values[item['id']]} for item in callback['state']],
            'changedPropIds': [changed],
        })
        self.assertEqual(response.status_code, 200, response.data)
        return response.get_json()['response']

    def test_registered_callbacks_process_254_counties_then_one_selected_detail(self):
        counties = [{**self.county, 'fips': str(48001 + i * 2)} for i in range(254)]
        response = self.call_callback('county-grid.rowData', {
            'county-table-day': {**self.day, 'counties': counties},
            'view-toggle': 'count', 'selected-model-store': 'seihrd-stochastic',
        }, 'county-table-day.data')
        self.assertEqual(len(response['county-grid']['rowData']), 254)
        self.assertNotIn('ageGroups', json.dumps(response))
        selection = self.call_callback('selected-county-store.data', {
            'county-grid': self.selected, 'selected-state-store': 'Texas', 'selected-county-store': None,
        }, 'county-grid.selectedRows')
        self.assertEqual(selection['selected-county-store']['data'], '48201')
        response = self.call_callback('county-age-title.children', {
            'selected-county-store': '48201', 'county-selected-age': self.request,
            'view-toggle': 'percent', 'selected-model-store': 'seihrd-stochastic',
            'county-grid': self.selected,
        }, 'county-selected-age.data')
        self.assertEqual(response['county-age-title']['children'], 'Harris — age breakdown')
        self.assertIn('6.8%', json.dumps(response))
        self.assertNotIn('county-grid', response)

    def test_legacy_expansion_is_not_registered(self):
        client = app.app.server.test_client()
        deps = client.get('/_dash-dependencies').get_json()
        self.assertFalse(any('expanded-counties' in item['output'] for item in deps))
        self.assertFalse(any('county-age-collapse' in item['output'] for item in deps))
        self.assertFalse(any('spread-table.children' in item['output'] for item in deps))


if __name__ == '__main__':
    unittest.main()
