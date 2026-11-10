"""Build starter provider-template DATA; never imported by Core at runtime.

Provider authors can distribute the same descriptor in an ordinary inert Agent
ZIP. Adding an uploaded template does not change Core or its Python registry.
"""
import argparse
import copy
import json
from pathlib import Path

from three_mm_protocol.character_display import CharacterDisplayProfileV1
from three_mm_protocol.character_display_package import manifest as display_manifest
from three_mm_protocol.gpio_input import GpioInputProfileV1, INPUT_FEATURE, BCM_PINS
from three_mm_protocol.gpio_input_package import manifest as input_manifest
from three_mm_protocol.hardware_templates import validate_template


def _text(key, label, default):
    return {'key': key, 'label': label, 'type': 'text', 'default': default,
            'maxlength': 64, 'pattern': '^[a-z][a-z0-9_.-]{0,63}$'}


def _number(key, label, default, low, high):
    return {'key': key, 'label': label, 'type': 'number', 'default': default, 'min': low, 'max': high}


def _select(key, label, default, options):
    return {'key': key, 'label': label, 'type': 'select', 'default': default,
            'options': [{'value': str(value), 'label': title} for value, title in options]}


def _document(manifest, descriptor):
    # A starter-template family has its own immutable package identity. Existing
    # installed providers are neither replaced nor adopted by a catalog read.
    prefix, digest = manifest['module_id'].rsplit('.', 1)
    manifest['module_id'] = prefix + '.profile.' + digest
    manifest['description'] = 'An exact, separately approved hardware profile.'
    manifest['registrations'][0]['metadata']['profile_template'] = True
    validate_template(manifest, descriptor)
    return {'manifest': manifest, 'template': descriptor,
            'health': 'Inert profile package; not hardware readiness.\n'}


def documents():
    for driver, rows in (('pcf8574', 2), ('pcf8574', 4), ('mock', 2)):
        profile = CharacterDisplayProfileV1(driver=driver, rows=rows, columns=20 if rows == 4 else 16)
        fields = [_text('display_id', 'Display ID', profile.display_id),
                  _number('columns', 'Columns', profile.columns, 1, 20 if rows == 4 else 40 if driver == 'pcf8574' else 80),
                  _number('bus', 'I²C bus', 1, 0, 255),
                  _select('address', 'I²C address', 39, [(n, f'0x{n:02X}') for n in range(32, 40)]),
                  {'key': 'backlight_active_high', 'label': 'Backlight active high', 'type': 'checkbox', 'default': True}]
        bindings = {field['key']: ['/configuration_defaults/'+field['key'], '/registrations/0/metadata/'+field['key']]
                    for field in fields}
        bindings['display_id'] = ['/configuration_defaults/display_id']
        for key in ('display_id', 'columns'):
            bindings[key] += ['/registrations/0/contract/'+path+'/properties/'+key+'/enum/0'
                             for path in ('state_schema', 'actions/write_frame/result_schema')]
        if driver == 'mock':
            fields.append(_select('rows', 'Rows', rows, [(n, str(n)) for n in (1, 2, 3, 4)]))
            bindings['rows'] = ['/configuration_defaults/rows', '/registrations/0/metadata/rows',
                '/registrations/0/contract/state_schema/properties/rows/enum/0',
                '/registrations/0/contract/actions/write_frame/result_schema/properties/rows/enum/0']
        identity = 'character-display.'+driver+('-'+str(rows)+'row' if driver == 'pcf8574' else '')
        descriptor = {'hardware_template_version': 1, 'template_id': identity,
            'name': f'HD44780 / PCF8574T · {rows} rows' if driver == 'pcf8574' else 'Character display (simulation)',
            'help': 'Prepare an immutable profile, then review installation separately. Disable the old provider before replacing it. Wiring and electrical levels are not verified by software.',
            'fields': fields, 'bindings': bindings}
        yield identity, _document(display_manifest(profile), descriptor)
    for driver in ('gpiod', 'mock'):
        profile = GpioInputProfileV1(driver=driver)
        descriptor = {'hardware_template_version': 1, 'template_id': 'gpio-input.'+driver,
            'name': 'GPIO digital input' + (' (simulation)' if driver == 'mock' else ' · contact to GND'),
            'help': 'Input only: connect GPIO to GND, never an external voltage. Pull-up and active-low; applications interpret edges. Disable the old input provider before changing its profile. Preparation does not install it or grant application event access.',
            'required_features': [INPUT_FEATURE],
            'fields': [_select('bcm_pin', 'Input GPIO (BCM numbering)', 17,
                              [(pin, f'GPIO{pin} / physical pin {physical}') for pin, physical in BCM_PINS.items()]),
                       _number('debounce_ms', 'Debounce (milliseconds)', 20, 0, 1000)],
            'bindings': {'bcm_pin': ['/configuration_defaults/inputs/gpio.input.1'],
                         'debounce_ms': ['/configuration_defaults/debounce_ms']}}
        yield descriptor['template_id'], _document(input_manifest(profile), descriptor)


def clock_documents():
    """Optional inert templates for Agents advertising finite local scenes.

    Uploadable data, not another Core driver registry. Existing static profiles
    keep their immutable identities and are never silently upgraded.
    """
    from three_mm_protocol.character_display_scene import CharacterDisplaySceneProfileV1, SCENE_FEATURE
    from three_mm_protocol.character_display_package import scene_manifest
    for identity, source in documents():
        if not identity.startswith('character-display.'):
            continue
        config = dict(source['manifest']['configuration_defaults'])
        config.pop('schema_version')
        profile = CharacterDisplaySceneProfileV1(**config)
        descriptor = copy.deepcopy(source['template'])
        descriptor['template_id'] = identity + '.local-clock'
        descriptor['name'] += ' · local clock'
        descriptor['required_features'] = [SCENE_FEATURE]
        descriptor['help'] += ' Local clock scenes require fresh application rights and expire within 30 seconds without renewal. A new profile must be approved separately.'
        for key in ('display_id', 'columns', 'rows'):
            if key not in descriptor['bindings']:
                continue
            descriptor['bindings'][key].append('/registrations/0/contract/actions/set_scene/result_schema/properties/'+key+'/enum/0')
        descriptor['bindings']['display_id'].append('/registrations/0/contract/actions/stop_scene/result_schema/properties/display_id/enum/0')
        yield descriptor['template_id'], _document(scene_manifest(profile), descriptor)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output-root', type=Path, default=Path(__file__).resolve().parents[1]/'backend/provider_templates')
    parser.add_argument('--local-clock', action='store_true', help='Generate separately reviewed clock templates instead of static/input templates')
    args = parser.parse_args()
    args.output_root.mkdir(parents=True, exist_ok=True)
    for name, value in (clock_documents() if args.local_clock else documents()):
        (args.output_root/(name+'.json')).write_text(json.dumps(value, sort_keys=True, indent=2)+'\n', encoding='utf-8')
        print(name)
