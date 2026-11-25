import argparse
import json
from pathlib import Path
from .audit import extract_archive,audit_dataset,file_hash
from .assets import fetch_assets
from .prepare import prepare,camera_review_template
from .engine import fixture,run,export
from ..export import write_json

SOURCE='https://universe.roboflow.com/datacar-my0w7/bien-so-xe-3w699-avdfe/dataset/1'

def main():
    parser=argparse.ArgumentParser(description='D05c local plate detector data audit and bounded CPU training; no application database access')
    sub=parser.add_subparsers(dest='command',required=True)
    p=sub.add_parser('fetch-model');p.add_argument('--output',type=Path,required=True)
    p=sub.add_parser('import-dataset');p.add_argument('--zip',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    p=sub.add_parser('audit');p.add_argument('--raw',type=Path,required=True);p.add_argument('--output',type=Path,required=True);p.add_argument('--source',default=SOURCE);p.add_argument('--version',default='1');p.add_argument('--license',default='CC-BY-4.0')
    p=sub.add_parser('camera-review');p.add_argument('--dataset',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    p=sub.add_parser('prepare');p.add_argument('--audit',type=Path);p.add_argument('--review',type=Path);p.add_argument('--camera-dataset',type=Path);p.add_argument('--camera-labels',type=Path);p.add_argument('--camera-review',type=Path);p.add_argument('--duplicate-reviews',type=Path);p.add_argument('--output',type=Path,required=True)
    p=sub.add_parser('fixture');p.add_argument('--output',type=Path,required=True)
    for name in ['compare','evaluate']:
        p=sub.add_parser(name);p.add_argument('--manifest',type=Path,required=True);p.add_argument('--plan',type=Path,required=True);p.add_argument('--model-manifest',type=Path,required=True);p.add_argument('--baseline-folder',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    for name in ['preflight','train','export']:
        p=sub.add_parser(name);p.add_argument('--manifest',type=Path,required=True);p.add_argument('--config',type=Path,required=True);p.add_argument('--assets',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
        if name=='export':p.add_argument('--checkpoint',type=Path,required=True)
        else:p.add_argument('--resume',type=Path);p.add_argument('--steps-this-run',type=int)
    args=parser.parse_args()
    if args.command=='fetch-model':result=fetch_assets(args.output);result={k:result[k] for k in ['model','source_revision','weights_sha256']}
    elif args.command=='import-dataset':
        args.output.mkdir(parents=True,exist_ok=False,mode=0o700)
        import shutil
        original=args.output/'original.zip';shutil.copyfile(args.zip,original);original.chmod(0o600)
        result=extract_archive(original,args.output/'raw');write_json(args.output/'import.json',{**result,'source':SOURCE,'version':'1','license':'CC-BY-4.0','original_path':str(args.zip.resolve())})
    elif args.command=='audit':
        result=audit_dataset(args.raw,args.output,source=args.source,version=args.version,license_name=args.license)
        result={'counts':result['counts'],'training_ready':result['training_ready'],'output':str(args.output)}
    elif args.command=='camera-review':result={'review_csv':str(camera_review_template(args.dataset,args.output))}
    elif args.command=='prepare':
        if bool(args.audit)!=bool(args.review):parser.error('--audit and --review must be paired')
        result=prepare(args.audit,args.review,args.output,camera_dataset=args.camera_dataset,camera_labels=args.camera_labels,camera_review=args.camera_review,duplicate_reviews=args.duplicate_reviews)
        result={k:result[k] for k in ['counts','batches_per_epoch','training_ready','blocking_issues']}
    elif args.command=='fixture':result=fixture(args.output);result={'purpose':result['purpose'],'samples':len(result['records'])}
    elif args.command in {'compare','evaluate'}:
        from .compare import compare
        result=compare(args.manifest,args.plan,args.model_manifest,args.baseline_folder,args.output)
        result={'split':result['split'],'images':result['images'],'output':str(args.output/'comparison.json')}
    elif args.command=='export':result=export(args.checkpoint,args.manifest,args.config,args.assets,args.output)
    else:
        if args.command=='train':
            m=json.loads(args.manifest.read_text())
            if m['purpose']!='reviewed_real_training':parser.error('train requires reviewed real data; fixture only supports preflight')
        result=run(args.manifest,args.config,args.assets,args.output,resume=args.resume,preflight=args.command=='preflight',steps_this_run=args.steps_this_run)
        result={k:result[k] for k in ['purpose','train_samples','train_boxes','batches_per_epoch','new_steps','total_steps','checkpoint_roundtrip','wall_seconds','cpu_seconds','rss_peak_observed_bytes']}
    print(json.dumps(result,ensure_ascii=False,indent=2))
