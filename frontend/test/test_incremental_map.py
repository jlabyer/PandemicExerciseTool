"""Run from frontend: python -m unittest discover -s test -p test_incremental_map.py."""

import copy
import json
import unittest

import dash
from plotly.utils import PlotlyJSONEncoder

import app  # noqa: F401
from pages import home


def geometry():
    return {'type': 'FeatureCollection', 'features': [
        {'type': 'Feature', 'properties': {'GEOID': fips, 'NAME': name},
         'geometry': {'type': 'Polygon', 'coordinates': [[
             [-100 + index, 30], [-99 + index, 30], [-99 + index, 31], [-100 + index, 30],
         ]]} }
        for index, (fips, name) in enumerate([('48001', 'Anderson'), ('48003', 'Andrews')])
    ]}


def apply_patch(figure, patch):
    result = copy.deepcopy(figure.to_plotly_json())
    for operation in patch.to_plotly_json()['operations']:
        assert operation['operation'] == 'Assign'
        destination = result
        for part in operation['location'][:-1]:
            destination = destination[part]
        destination[operation['location'][-1]] = operation['params']['value']
    return result


class IncrementalMapTests(unittest.TestCase):
    def setUp(self):
        self.geojson = geometry()
        self.figure, _, _, _, self.metadata = home.initialize_incremental_map(
            {'geojson': self.geojson}, 'Texas',
        )

    def frame(self, view='count'):
        return {
            'state': 'Texas', 'day': 7, 'view': view,
            'values': [10, 20] if view == 'count' else [1, 2],
            'customdata': [['Anderson', 10, 1, 0], ['Andrews', 20, 2, 1]],
            'highlight': {'lon': [], 'lat': []},
        }

    def test_initial_map_has_fixed_locations_and_reserved_highlight(self):
        self.assertEqual(self.metadata['fips'], ['48001', '48003'])
        self.assertEqual(self.figure.layout.uirevision, 'Texas')
        self.assertEqual(len(self.figure.data), 2)
        self.assertEqual(list(self.figure.data[1].lon), [])

    def test_count_and_percentage_patches_match_legacy_map(self):
        counties = [
            {'fips': '48001', 'infected': 10, 'infectedPercent': 1, 'deceased': 0},
            {'fips': '48003', 'infected': 20, 'infectedPercent': 2, 'deceased': 1},
        ]
        for view in ('count', 'percent'):
            with self.subTest(view=view):
                patch, title = home.update_map_incrementally(self.frame(view), self.metadata)
                updated = apply_patch(self.figure, patch)
                old = home._create_jurisdiction_choropleth(
                    [{'counties': counties}], 0, view, self.geojson, 'seihrd-stochastic', 'Texas',
                ).to_plotly_json()
                for key in ('z', 'zmax', 'colorbar', 'customdata'):
                    self.assertEqual(updated['data'][0][key], old['data'][0][key])
                self.assertEqual(title, 'Epidemic Simulation (Day 7)')
                self.assertEqual(updated['layout'], self.figure.to_plotly_json()['layout'])
                self.assertEqual(updated['data'][0]['geojson'], self.geojson)

    def test_selection_is_patched_and_cleared_without_touching_viewport(self):
        frame = self.frame()
        lon, lat = home._county_boundary_lines(self.geojson, '48001')
        frame['highlight'] = {'lon': lon, 'lat': lat}
        patch, _ = home.update_map_incrementally(frame, self.metadata)
        updated = apply_patch(self.figure, patch)
        self.assertEqual(updated['data'][1]['lon'], lon)
        clear, _ = home.update_map_incrementally(self.frame(), self.metadata)
        cleared = apply_patch(self.figure, clear)
        self.assertEqual(cleared['data'][1]['lon'], [])
        self.assertFalse(any(op['location'][0] == 'layout' for op in patch.to_plotly_json()['operations']))

    def test_missing_assets_and_state_switch(self):
        figure, style, _, _, metadata = home.initialize_incremental_map({}, 'Texas')
        self.assertFalse(figure.data)
        self.assertEqual(style, {'display': 'none'})
        self.assertIsNone(metadata)
        patch, _ = home.update_map_incrementally(self.frame(), {'state': 'Delaware'})
        self.assertIs(patch, dash.no_update)
        _, _, _, _, metadata = home.initialize_incremental_map(
            {'geojson': self.geojson, 'jurisdiction': 'Texas'}, 'Delaware',
        )
        self.assertEqual(metadata['state'], 'Texas')

    def test_patch_payload_excludes_boundaries_and_viewport(self):
        patch, _ = home.update_map_incrementally(self.frame(), self.metadata)
        payload = json.dumps(patch, cls=PlotlyJSONEncoder)
        self.assertNotIn('geojson', payload)
        self.assertNotIn('mapbox', payload)
        self.assertNotIn('locations', payload)

    def test_registered_callback_never_receives_history_or_full_figure(self):
        client = app.app.server.test_client()
        self.assertEqual(client.get('/_dash-layout').status_code, 200)
        key = next(key for key, callback in app.app.callback_map.items()
                   if any(item['id'] == 'map-frame' for item in callback['inputs']))
        callback = app.app.callback_map[key]
        self.assertEqual([item['id'] for item in callback['inputs']], ['map-frame'])
        self.assertEqual([item['id'] for item in callback['state']], ['map-metadata'])
        response = client.post('/_dash-update-component', json={
            'output': key,
            'outputs': [{'id': 'spread-map', 'property': 'figure'},
                        {'id': 'epidemic-progress-title', 'property': 'children'}],
            'inputs': [{'id': 'map-frame', 'property': 'data', 'value': self.frame()}],
            'state': [{'id': 'map-metadata', 'property': 'data', 'value': self.metadata}],
            'changedPropIds': ['map-frame.data'],
        })
        self.assertEqual(response.status_code, 200, response.data)
        self.assertIn(b'__dash_patch_update', response.data)
        self.assertNotIn(b'geojson', response.data)


if __name__ == '__main__':
    unittest.main()
