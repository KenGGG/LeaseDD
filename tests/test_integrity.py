import hashlib,json
from leasedd.integrity import verify_files

def test_restored_files_require_original_hash_and_manifest(tmp_path):
 raw=tmp_path/'raw';raw.write_bytes(b'original')
 output=tmp_path/'exports';output.mkdir();report=output/'report_review.docx';report.write_bytes(b'report')
 sha=hashlib.sha256(b'report').hexdigest();manifest={'output_sha256':sha,'run_id':'task'}
 (output/'artifact_manifest.json').write_text(json.dumps(manifest))
 sources=[{'path':'raw','sha256':hashlib.sha256(b'original').hexdigest()}]
 exports=[{'path':'exports/report_review.docx','sha256':sha,'manifest':manifest}]
 assert verify_files(tmp_path,sources,exports)==[]
 raw.write_bytes(b'tampered')
 assert verify_files(tmp_path,sources,exports)==['source_integrity_failed:raw']
 raw.write_bytes(b'original');(output/'artifact_manifest.json').write_text('{}')
 assert verify_files(tmp_path,sources,exports)==['export_integrity_failed:exports/report_review.docx']
