"""Frontend smoke tests. API tests require a backend running on localhost:8000.

Run from frontend: python -m pytest test/test_app.py
"""

import json
import time

import requests


def test_backend_connection():
    """The backend's simulation list is accessible without resetting its state."""
    response = requests.get('http://localhost:8000/api/pet/', timeout=10)
    assert response.status_code == 200, response.text


def test_simulation_api():
    """Create and start a simulation, check output access, then stop the task."""
    params = {
        'disease_name': 'COVID-19',
        'model_type': 'seirs-deterministic',
        'state': 'Texas',
        'R0': 2.5,
        'beta_scale': 1.0,
        'tau': 5.1,
        'kappa': 1.0,
        'gamma': 0.1,
        'chi': 0.5,
        'rho': 0.8,
        'nu': '0.01,0.01,0.01,0.01,0.01',
        'sigma': '1,1,1,1,1',
        'infectious_period': 7,
        'immune_period': 0,
        'initial_infected': json.dumps([
            {'county': '48201', 'infected': 100, 'age_group': '2'},
        ]),
        'npis': json.dumps([]),
        'vaccine_model': json.dumps({}),
    }

    response = requests.post('http://localhost:8000/api/pet/', json=params, timeout=10)
    assert response.status_code == 201, response.text
    sim_id = response.json().get('id')
    assert sim_id is not None, 'Simulation creation response is missing its id'

    run_response = requests.get(f'http://localhost:8000/api/pet/{sim_id}/run', timeout=10)
    task_id = run_response.json().get('task_id') if run_response.status_code == 202 else None
    try:
        assert run_response.status_code == 202, run_response.text
        assert task_id, 'Simulation run response is missing its task_id'

        time.sleep(2)
        output_response = requests.get('http://localhost:8000/api/output/0', timeout=10)
        # This checks endpoint access; output may not have been generated yet.
        assert output_response.status_code in (200, 404), output_response.text
    finally:
        if task_id:
            cleanup_response = requests.get(
                f'http://localhost:8000/api/delete/{task_id}', timeout=10,
            )
            assert cleanup_response.status_code == 200, cleanup_response.text


def test_data_loading():
    """County data produces matching dropdown options."""
    from test.data_loader import DataLoader

    loader = DataLoader()
    counties = loader.load_texas_counties()
    assert counties, 'Expected at least one county'
    assert all({'name', 'fips', 'population'} <= county.keys() for county in counties)

    options = loader.get_county_dropdown_options()
    assert options == [
        {'label': county['name'], 'value': county['fips']} for county in counties
    ]


def test_visualization():
    """The current Dash renderers handle an empty simulation."""
    import app  # noqa: F401 - Register Dash pages before importing their callbacks.
    from pages import home

    empty_map = home._create_empty_map()
    assert not empty_map.data
    assert empty_map.layout.height == 400

    empty_chart = home._build_chart_figure([], 0, 'seirs-deterministic')
    assert not empty_chart.data
    assert empty_chart.layout.title.text == 'Epidemic Curve - No Data Available'

    rows, columns, controls = home.update_county_grid(None, 'percent', 'seirs-deterministic')
    assert rows == []
    assert columns[2]['headerName'] == 'Recovered'
    assert controls == {'display': 'none'}
