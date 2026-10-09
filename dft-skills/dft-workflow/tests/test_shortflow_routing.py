"""Maintain the small skill surface and actual reference routing."""
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[2]


def test_workflow_routes_submission_policy_instead_of_defining_launcher():
    text = (ROOT / 'dft-workflow/SKILL.md').read_text(encoding='utf-8')
    assert 'dft-submit' in text
    assert 'bind-approval' in text and '--draft' in text
    assert 'job.script' in text
    assert 'bare `srun`' not in text
    assert '-pd .true.' not in text
    assert len(text.splitlines()) < 110


def test_task_mode_and_wannier_are_conditionally_routed():
    design = (ROOT / 'dft-design/SKILL.md').read_text(encoding='utf-8')
    wannier = (ROOT / 'dft-wannier/SKILL.md').read_text(encoding='utf-8')
    assert 'user_specified' in design and 'design_mode' in design
    assert 'dft-submit' in wannier
    assert len(design.splitlines()) < 100


def test_skill_reference_links_resolve():
    for skill in ('dft-design', 'dft-workflow', 'dft-analysis', 'dft-work-manager', 'dft-wannier'):
        path = ROOT / skill / 'SKILL.md'
        text = path.read_text(encoding='utf-8')
        for target in re.findall(r'\]\((references/[^)#]+)(?:#[^)]*)?\)', text):
            assert (path.parent / target).is_file(), (skill, target)
