from pathlib import Path
import os
import input_reconciliation as ir
from test_input_reconciliation import _write_vasp_inputs, _write_qe_input, _make_vasp_task


def test_vasp_unchanged_files_reuse_semantics_and_changed_file_reparses(tmp_path, monkeypatch):
    _write_vasp_inputs(tmp_path)
    first = ir.parse_current_inputs('vasp', tmp_path)
    original = ir._parse_incar
    calls = []
    monkeypatch.setattr(ir, '_parse_incar', lambda text: (calls.append('INCAR'), original(text))[1])
    for name in ('_parse_poscar', '_parse_potcar', '_parse_vasp_kpoints'):
        monkeypatch.setattr(ir, name, lambda text: (_ for _ in ()).throw(AssertionError('unchanged reparse')))
    second = ir.parse_current_inputs('vasp', tmp_path, previous_snapshot=first)
    assert calls == [] and second['parameters'] == first['parameters']
    path = tmp_path / 'INCAR'
    stamp = path.stat()
    path.write_text(path.read_text().replace('520', '530'))
    os.utime(path, ns=(stamp.st_atime_ns, stamp.st_mtime_ns))
    third = ir.parse_current_inputs('vasp', tmp_path, previous_snapshot=second)
    assert calls == ['INCAR'] and third['parameters']['ENCUT'] == 530
    assert third['file_hashes']['INCAR'] != first['file_hashes']['INCAR']


def test_qe_cache_reparses_only_changed_input(tmp_path, monkeypatch):
    _write_qe_input(tmp_path)
    (tmp_path / 'dos.in').write_text('&DOS\n Emin=-3, Emax=3,\n/\n')
    first = ir.parse_current_inputs('quantum-espresso', tmp_path, 'scf.in')
    original = ir._parse_qe_blocks
    calls = []
    monkeypatch.setattr(ir, '_parse_qe_blocks', lambda texts: (calls.extend(texts), original(texts))[1])
    second = ir.parse_current_inputs('quantum-espresso', tmp_path, 'scf.in', previous_snapshot=first)
    assert calls == [] and second['parameters'] == first['parameters']
    (tmp_path / 'dos.in').write_text('&DOS\n Emin=-5, Emax=3,\n/\n')
    third = ir.parse_current_inputs('quantum-espresso', tmp_path, 'scf.in', previous_snapshot=second)
    assert len(calls) == 1 and third['parameters']['emin'] == -5
    assert third['file_semantics']['QE_INPUT'] == first['file_semantics']['QE_INPUT']


def test_invalid_cache_version_is_not_trusted(tmp_path, monkeypatch):
    _write_vasp_inputs(tmp_path)
    first = ir.parse_current_inputs('vasp', tmp_path)
    first['parser_cache']['version'] = -1
    original = ir._parse_incar
    calls = []
    monkeypatch.setattr(ir, '_parse_incar', lambda text: (calls.append(1), original(text))[1])
    ir.parse_current_inputs('vasp', tmp_path, previous_snapshot=first)
    assert calls == [1]


def test_reconciliation_reuses_persisted_snapshot(tmp_path, monkeypatch):
    task, design, _ = _make_vasp_task(tmp_path)
    ir.reconcile_task(task, design, write=True)
    def no_parse(text):
        raise AssertionError('persisted unchanged input was reparsed')
    monkeypatch.setattr(ir, '_parse_incar', no_parse)
    assert ir.reconcile_task(task, design, write=True)['verdict'] == 'ADVANCE'


def test_qe_per_file_composition_matches_original_multi_file_parser(tmp_path):
    _write_qe_input(tmp_path)
    extra = '&SYSTEM\n ecutwfc=75,\n/\nCELL_PARAMETERS angstrom\n2 0 0\n0 2 0\n0 0 2\n'
    (tmp_path / 'extra.in').write_text(extra)
    texts = [(tmp_path / 'scf.in').read_text(), extra]
    params, semantics = ir._parse_qe_blocks(texts)
    result = ir.parse_current_inputs('qe', tmp_path, 'scf.in')
    assert result['parameters'] == params
    assert result['file_semantics']['QE_INPUT'] == semantics
