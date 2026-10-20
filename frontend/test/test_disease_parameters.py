"""Run from frontend: python -m unittest discover -s test -p test_disease_parameters.py."""

import json
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

import dash

import app  # noqa: F401 - Register Dash pages before importing their callbacks.
from constants import AGE_GROUPS, MODEL_OPTIONS, SEIHRD_DEFAULTS
from pages import home


def components(component):
    yield component
    children = getattr(component, 'children', None)
    if children is not None:
        for child in children if isinstance(children, (list, tuple)) else [children]:
            yield from components(child)


class DiseaseParameterTests(unittest.TestCase):
    def inputs(self, model='seihrd-stochastic', preset=None):
        modal = home.update_disease_param_modal_body(model, preset, True)
        return {
            component.id['param']: component
            for component in components(modal)
            if isinstance(getattr(component, 'id', None), dict)
            and component.id['type'] == 'dp-input'
        }

    def save(self, inputs, model='seihrd-stochastic'):
        states = [{'id': component.id} for component in inputs.values()]
        with patch.object(home, 'ctx', SimpleNamespace(states_list=[states])):
            return home.save_disease_parameters(
                1, [component.value for component in inputs.values()], [], model
            )[0]

    def test_model_option_and_modal_defaults(self):
        self.assertIn('seihrd-stochastic', [option['value'] for option in MODEL_OPTIONS])
        self.assertNotIn('seihrd-deterministic', [option['value'] for option in MODEL_OPTIONS])
        inputs = self.inputs()
        self.assertNotIn('latent-period', inputs)
        for param, default in SEIHRD_DEFAULTS.items():
            if isinstance(default, list):
                self.assertEqual(len(default), len(AGE_GROUPS))
                self.assertEqual([inputs[f'{param}-{i}'].value for i in range(len(default))], default)
            else:
                self.assertEqual(inputs[param].value, default)
        self.assertGreater(inputs['E_to_IPandIA_days'].min, 0)
        self.assertEqual(inputs['prop_E_to_IA-0'].max, 1)
        self.assertIs(home.update_disease_param_modal_body('seihrd-stochastic', {}, False), dash.no_update)

    def test_empty_catalog(self):
        modal = home.update_disease_param_modal_body('seihrd-stochastic', {}, True)
        catalog = next(c for c in components(modal) if getattr(c, 'id', None) == {
            'type': 'dp-dropdown', 'param': 'preset',
        })
        self.assertEqual(catalog.options, [])
        self.assertTrue(catalog.disabled)

    def test_save_custom_values_and_zero_proportions(self):
        preset = {param: [8.5 if param.endswith('_days') else 0] * len(default)
                  if isinstance(default, list) else 8.5
                  for param, default in SEIHRD_DEFAULTS.items()}
        preset.update(R0=0, disease_name='Custom SEIHRD', rel_inf_IA_to_IS=0)
        saved = self.save(self.inputs(preset=preset))
        for param in SEIHRD_DEFAULTS:
            self.assertEqual(saved[param], preset[param])
        self.assertEqual(saved['R0'], 0)
        self.assertEqual(saved['scenario_name'], 'Custom SEIHRD')

    def test_blank_fields_use_defaults(self):
        inputs = self.inputs()
        inputs['IP_to_IS_days'].value = None
        inputs['H_to_R_days-0'].value = None
        inputs['prop_H_to_D-0'].value = 0
        saved = self.save(inputs)
        self.assertEqual(saved['IP_to_IS_days'], SEIHRD_DEFAULTS['IP_to_IS_days'])
        self.assertEqual(saved['H_to_R_days'][0], SEIHRD_DEFAULTS['H_to_R_days'][0])
        self.assertEqual(saved['prop_H_to_D'][0], 0)

    def test_payload_contains_saved_seihrd_fields(self):
        inputs = self.inputs()
        inputs['H_to_R_days-0'].value = 9.25
        inputs['prop_H_to_D-0'].value = 0
        saved = self.save(inputs)
        created = Mock(status_code=201, text='created')
        created.json.return_value = {'id': 1}
        started = Mock(status_code=202, text='started')
        started.json.return_value = {'task_id': 'test-task'}
        with patch.object(home.requests, 'post', return_value=created) as post, \
             patch.object(home.requests, 'get', return_value=started):
            result = home.toggle_simulation(
                1, {}, saved, [], [], {}, {}, [], False, False,
                'seihrd-stochastic', 'Illinois',
            )
        self.assertTrue(result[0]['isRunning'])
        payload = post.call_args.kwargs['json']
        for param, default in SEIHRD_DEFAULTS.items():
            value = payload[param]
            if isinstance(default, list):
                value = [float(x) for x in value.split(',')] if param == 'sigma' else json.loads(value)
            self.assertEqual(value, saved[param])

    def test_existing_models_keep_their_fields(self):
        for model in ('seaitrd-deterministic', 'seaitrd-stochastic', 'seirs-deterministic', 'seirs-stochastic'):
            with self.subTest(model=model):
                inputs = self.inputs(model)
                self.assertIn('latent-period', inputs)
                self.assertNotIn('E_to_IPandIA_days', inputs)
                saved = self.save(inputs, model)
                self.assertEqual(saved['model_type'], model)
                self.assertNotIn('prop_H_to_D', saved)

    def test_seihrd_summary_shows_saved_parameters_and_initial_cases(self):
        inputs = self.inputs(preset={'disease_name': 'SEIHRD scenario', 'R0': 2.8})
        inputs['E_to_IPandIA_days'].value = 1.5
        inputs['H_to_R_days-0'].value = 9.25
        inputs['prop_H_to_D-0'].value = 0
        inputs['rel_inf_IA_to_IS'].value = 0
        saved = self.save(inputs)
        display = home.create_scenario_display(saved, [{
            'cases': 10, 'age_group': '18-49 years', 'location': 'Cook County',
        }])
        text = ' '.join(str(c) for c in components(display) if isinstance(c, (str, int, float)))
        self.assertIn('Disease Parameters', text)
        self.assertIn('Scenario:  SEIHRD scenario', text)
        self.assertIn('Reproduction Number:  2.8', text)
        self.assertIn('Latent Period:  1.5 days', text)
        self.assertIn('Relative Asymptomatic Infectiousness:  0', text)
        lists = [c for c in components(display) if isinstance(c, home.html.Ul)]
        self.assertEqual(len(lists), 6)  # Five age-specific parameters and initial cases.
        self.assertEqual([li.children for li in lists[0].children], [
            '0-4 years: 9.25 days', '5-17 years: 4.8 days', '18-49 years: 6.2 days',
            '50-64 years: 6.8 days', '65+ years: 6.55 days',
        ])
        self.assertEqual(lists[3].children[0].children, '0-4 years: 0')
        self.assertIn('Initial Cases', text)
        self.assertIn('10 aged 18-49 years in Cook County', text)

    def test_seihrd_summary_without_initial_cases(self):
        display = home.create_scenario_display(self.save(self.inputs()), [])
        text = ' '.join(c for c in components(display) if isinstance(c, str))
        self.assertIn('Disease Parameters', text)
        self.assertIn('Hospital Admission to Recovery:', text)
        self.assertNotIn('No scenario set yet.', text)
        self.assertNotIn('Initial Cases', text)


if __name__ == '__main__':
    unittest.main()
