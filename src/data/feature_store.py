"""Immutable Feature Store publication and provider-neutral Signal retrieval.

Uses the platform's existing catalog paths, content-addressed payloads and atomic
installer. A complete materialization manifest is published only after validation;
Signal Library entries are link-only projections installed last.
"""
from contextlib import contextmanager
from copy import deepcopy
import fcntl
import json
from pathlib import Path

from jsonschema import Draft202012Validator, FormatChecker
from research.performance import measure
from data.alfred_onboarding import Store, stable_read, strict_json
from data.transformations.contracts import normalize_reference, normalize_result, token
from data.transformations.identity import (canonical_bytes, digest, reference,
    feature_id, signal_id, execution_materialization_key, normalize_bindings)
from data.feature_store_contracts import (validate_record, normalize_materialization,
    normalize_library_entry, normalize_pit_operand, semantic_rows_digest,
    make_materialization_id_from_key)


class PublicationError(ValueError):
    pass


class InterruptedPublication(RuntimeError):
    """Test fault injection; never used to damage an existing publication."""


def materialization_path(identifier):
    token(identifier)
    if not identifier.startswith('MATERIALIZATION_'):raise PublicationError('Wrong materialization ID')
    return f'storage/catalog/feature_store/{identifier}/manifest.json'


def record_path(record):
    kind,identifier,version=record['record_type'],record['id'],record['version']
    token(identifier)
    folders={'feature_recipe_definition':'feature_recipes','feature_definition':'features','dataset_definition':'datasets','source_view_definition':'source_views',
             'transformation_definition':'transformations','policy_definition':'policies','provider_contract':'providers',
             'scope_definition':'scopes'}
    if kind in folders:return f'definitions/{folders[kind]}/{identifier}/{version}.json'
    if kind=='feature_recipe_registration':return f'storage/catalog/feature_recipes/{identifier}/manifest.json'
    if kind=='materialization_manifest':return materialization_path(identifier)
    if kind in ('lineage_manifest','pit_operand_record','fx_feature_input_record','fx_feature_lineage_record'):return f'storage/catalog/lineage/{identifier}/manifest.json'
    if kind=='implementation_manifest':return f'storage/catalog/implementations/{identifier}/manifest.json'
    if kind=='snapshot_manifest':return f'storage/catalog/snapshots/{identifier}/manifest.json'
    if kind=='onboarding_evidence':return f'storage/catalog/onboarding/evidence/{identifier}.json'
    if kind=='ingestion_receipt':return f'storage/catalog/ingestions/records/{identifier}.json'
    if kind=='capability_assessment':return f'storage/catalog/readiness/records/{identifier}.json'
    if kind=='signal_library_entry':
        return f"storage/catalog/signal_library/entries/{record['signal_id']}/{digest(record)}.json"
    raise PublicationError('Unsupported canonical record type: '+kind)


class FeatureStore:
    def __init__(self, root):
        self.root=Path(root).resolve()
        self.io=Store(self.root)
        self._resolved={}
        self._resolved_capture={}
        self._payloads={}
        self._native_rows={}
        from data.lineage_packs import PackedLineage
        self._packed_lineage=PackedLineage(self)

    def path(self, relative):
        path=self.root/relative
        if path.is_symlink() or not path.resolve().is_relative_to(self.root):raise PublicationError('Catalog path leaves platform')
        return path

    def _validate(self, record):
        version=record.get('schema_version')
        if version=='0.7.0':
            from data.reusable_feature_contracts import validate_record as validate_reusable_feature
            return validate_reusable_feature(record)
        if version=='0.6.0':
            from data.fx_feature_contracts import validate_record as validate_fx_feature
            return validate_fx_feature(record)
        if version=='0.5.0':
            from data.fx_records import validate_record as validate_fx
            return validate_fx(record)
        if version=='0.3.0':return validate_record(record)
        name={'0.1.0':'onboarding.schema.json','0.2.0':'platform.schema.json'}.get(version)
        if name is None:raise PublicationError('Unsupported record schema')
        schema=strict_json(stable_read(self.path('specs/schemas/'+name)))
        Draft202012Validator(schema,format_checker=FormatChecker()).validate(record)
        return record

    def install_record(self, record):
        self._validate(record)
        self.io.install(record_path(record),canonical_bytes(record)+b'\n')
        return reference(record)

    @measure('catalog.feature_resolution')
    def resolve(self, binding):
        from data.verified_inputs import record_memo
        # Window-specific causal lineage can dwarf the useful input cache and is
        # not shared across horizons once the materialization itself is verified.
        if str(binding.get('id', '')).startswith(('LINEAGE_', 'PIT_OPERAND_', 'MATERIALIZATION_')):
            return self._resolve_record(binding)
        # Repeated small definitions within one verifier share its complete
        # checked read set. A different read still validates every witness.
        return record_memo(self.root, 'feature_record', binding, lambda: self._resolve_record(binding),
                           within_capture=True)

    def _resolve_record(self, binding):
        from data.verified_inputs import current, dependency_capture, probe, probe_definition, compact_memo, phase_active
        normalize_reference(binding)
        key=(binding['id'],binding['version'],binding['content_sha256'])
        capture=dependency_capture()
        if key in self._resolved and (current(self.root) is None or
                (capture is not None and self._resolved_capture.get(key) is capture)):
            return deepcopy(self._resolved[key])
        identifier,version=binding['id'],binding['version']
        relative=None
        matches=[]
        folders=('feature_recipes','features','datasets','source_views','transformations','policies','providers','scopes')
        def inventory():
            result={}
            for folder in folders:
                path=self.path('definitions/'+folder);probe(path)
                result[folder]={p.name:True for p in path.iterdir()} if path.exists() else {}
            return result
        # Exact directory membership proves the many negative catalog lookups.
        # A newly added identifier invalidates this bounded, phase-local index.
        # Existing identifiers still take the ordinary version/file checks.
        names=(compact_memo(self.root,'definition_directory_membership',{},inventory,within_capture=True)
               if phase_active(self.root) else None)
        for folder in folders:
            if names is not None and identifier not in names[folder]:continue
            candidate=f'definitions/{folder}/{identifier}/{version}.json'
            candidate_path=self.path(candidate)
            probe_definition(candidate_path)
            if candidate_path.is_file():matches.append(candidate)
        if len(matches)>1:raise PublicationError('Ambiguous definition identity')
        if matches:relative=matches[0]
        if relative is None:
            catalogs={'FEATURE_RECIPE_REGISTRATION_':'feature_recipes','MATERIALIZATION_':'feature_store','LINEAGE_':'lineage','PIT_OPERAND_':'lineage','IMPLEMENTATION_':'implementations','SNAPSHOT_':'snapshots'}
            for prefix,folder in catalogs.items():
                if identifier.startswith(prefix):relative=f'storage/catalog/{folder}/{identifier}/manifest.json';break
        if relative is None:
            catalogs={'EVIDENCE_':'onboarding/evidence','INGESTION_':'ingestions/records','READINESS_':'readiness/records'}
            for prefix,folder in catalogs.items():
                if identifier.startswith(prefix):relative=f'storage/catalog/{folder}/{identifier}.json';break
        if relative is None:raise PublicationError('Unsupported immutable reference kind: '+identifier)
        loose = self.path(relative)
        probe(loose)
        packed = self._packed_lineage.resolve(binding, rebuild_missing=not loose.exists()) if identifier.startswith('LINEAGE_') else None
        loose_present = loose.exists()
        record = strict_json(stable_read(loose)) if loose_present else packed
        if record is None:
            raise FileNotFoundError(loose)
        if packed is not None and record != packed:
            raise PublicationError('Conflicting loose and packed lineage')
        # PackedLineage has already validated every row's schema, canonical
        # bytes and exact reference before returning a private copy. Repeating
        # that identical row validation here adds no evidence. Loose records
        # still need their own validation, even when an equal pack also exists.
        if packed is None or loose_present:
            self._validate(record)
            if reference(record)!=binding:raise PublicationError('Immutable reference or path mismatch')
        if record_path(record)!=relative:raise PublicationError('Immutable reference or path mismatch')
        # Materializations contain every row-lineage reference. Catalog scans
        # must not retain the entire observation population in this store.
        # Exact numerical reuse is bounded separately by verified_inputs.
        if not identifier.startswith('MATERIALIZATION_'):
            self._resolved[key]=deepcopy(record)
            if capture is not None:self._resolved_capture[key]=capture
            else:self._resolved_capture.pop(key,None)
        return record

    def payload(self, member):
        from data.verified_inputs import memo
        key = {name: member[name] for name in ('blob_sha256', 'format', 'byte_count')}
        return memo(self.root, 'payload', key, lambda: self._verified_payload(member))

    def _verified_payload(self, member):
        from data.verified_inputs import current
        relative=f"storage/payloads/sha256/{member['blob_sha256'][:2]}/{member['blob_sha256']}.{member['format']}"
        if relative not in self._payloads or current(self.root) is not None:
            if self.path(relative).is_file():
                self._payloads[relative]=stable_read(self.path(relative),member['blob_sha256'])
            else:
                from data.fx_records import resolve_external_payload
                self._payloads[relative]=resolve_external_payload(self,member)
        data=self._payloads[relative]
        if len(data)!=member['byte_count']:raise PublicationError('Payload byte count mismatch')
        return data

    def verify_closure(self, records):
        from data.verified_inputs import verified_read
        seen=set()
        def visit(value):
            if isinstance(value,dict):
                if set(value)=={'id','version','content_sha256'}:
                    key=tuple(value[k] for k in ('id','version','content_sha256'))
                    if key not in seen:
                        seen.add(key);visit(self.resolve(value))
                    return
                if 'blob_sha256' in value and 'format' in value and 'byte_count' in value:self.payload(value)
                if value.get('record_type') in ('onboarding_evidence','ingestion_receipt') and value.get('schema_version')!='0.5.0':
                    p=value['body']['payload'];self.payload({'blob_sha256':p['sha256'],'format':'json','byte_count':p['byte_count']})
                if value.get('record_type')=='pit_operand_record':self.resolve_operand(value)
                for child in value.values():visit(child)
            elif isinstance(value,list):
                for child in value:visit(child)
        # Accept the complete closure only after rechecking its exact read set.
        # Publication happens in the caller after this context has succeeded.
        with verified_read(self.root):
            for record in records:visit(record)

    def resolve_operand(self, record_or_ref):
        record=self.resolve(record_or_ref) if set(record_or_ref)=={'id','version','content_sha256'} else record_or_ref
        normalize_pit_operand(record)
        body=record['body'];snapshot=self.resolve(body['pit_snapshot'])
        view=self.resolve(body['source_view']);dataset=self.resolve(body['dataset'])
        if snapshot['definition']!=body['source_view'] or view['body']['dataset']!=body['dataset'] or body['raw_snapshot'] not in snapshot['upstream_snapshots']:
            raise PublicationError('Operand source definition/snapshot relationship mismatch')
        # Native row field names are pinned data, not provider dispatch logic.
        found=[]
        if snapshot['id'] not in self._native_rows:
            rows=[]
            for member in snapshot['members']:
                if member['format']!='jsonl':raise PublicationError('Operand snapshot requires canonical JSONL')
                rows.extend(strict_json(line) for line in self.payload(member).splitlines())
            if len(rows)!=snapshot['record_count'] or digest(rows)!=snapshot['semantic_content_sha256']:
                raise PublicationError('Operand PIT snapshot semantic integrity failure')
            self._native_rows[snapshot['id']]=rows
        for row in self._native_rows[snapshot['id']]:
            if all(row.get(item['field'])==item['value'] for item in body['pit_row_key']):found.append(row)
        if len(found)!=1 or digest(found[0])!=body['pit_row_sha256']:raise PublicationError('Operand row locator does not resolve exactly')
        row=found[0];mapping=body['field_mapping'];context=body['key']
        for name in ('entity_id','reference_time','available_at'):
            if row.get(mapping[name])!=context[name]:raise PublicationError('Operand canonical key differs from its native row')
        for name in ('raw_snapshot','source_view'):
            if row.get(mapping[name])!=body[name]:raise PublicationError('Operand row has different source references')
        if row.get(mapping['raw_blob_sha256'])!=body['raw_cell']['blob_sha256'] or row.get(mapping['raw_value_field'])!=body['raw_cell']['field'] or row.get(mapping['temporal_precision'])!=body['temporal_precision']:
            raise PublicationError('Operand raw cell or precision differs from its native row')
        raw_selector={item['field']:item['value'] for item in body['raw_cell']['row_key']}
        for item in body['raw_row_mapping']:
            if row.get(item['pit_field'])!=raw_selector[item['raw_field']]:
                raise PublicationError('Raw row selector differs from its resolved native PIT row')
        fields={field['name']:field for field in dataset['body']['fields']}
        if context['measure']!=mapping['value'] or context['measure'] not in fields or context['entity_id'] not in dataset['body']['economic_entity_ids']:
            raise PublicationError('Operand measure/entity is outside its registered dataset')
        # Raw-cell coordinates remain a source-evidence locator. Retrieval uses
        # canonical PIT rows and never needs a provider payload parser.
        raw=self.resolve(body['raw_snapshot'])
        if body['raw_cell']['blob_sha256'] not in {m['blob_sha256'] for m in raw['members']}:
            raise PublicationError('Raw cell blob is not a member of its pinned snapshot')
        return {'record':record,'pit_row':found[0]}

    @contextmanager
    def writer(self):
        path=self.path('storage/temporary/feature-store-publication.lock');path.parent.mkdir(parents=True,exist_ok=True)
        with path.open('a+b') as lock:
            with measure('lock.wait.feature_publication'):
                fcntl.flock(lock,fcntl.LOCK_EX)
            try:yield
            finally:fcntl.flock(lock,fcntl.LOCK_UN)


def _key(row):
    return {k:row[k] for k in ('entity_id','reference_time','evaluation_cutoff')}


def _lineage(inputs, operation, implementation, bindings):
    record={'schema_version':'0.2.0','record_type':'lineage_manifest','version':'1.0.0',
        'inputs':inputs,'operation':operation,'implementation':implementation,'policy_bindings':bindings}
    record['id']='LINEAGE_'+digest(record)
    return record


def _verify_outputs(store, feature, metadata, implementation_ref, bindings, rows, lineages, source_snapshots):
    recipe=feature['body']['recipe']
    if len(recipe['steps'])!=1:raise PublicationError('This initial publisher supports the single monthly fractional-change recipe only')
    step=recipe['steps'][0];operator=store.resolve(step['operator'])
    if operator['body']['execution_contract']['kernel']!='change.pct' or step['parameters']!=[{'name':'k','unit':'observations','value':{'kind':'integer','value':'1'}}] or metadata['cadence']['frequency']!='monthly':
        raise PublicationError('Unsupported initial Feature Store operation contract')
    if metadata['source_view']!=recipe['sources'][0]['source_view'] or metadata['selection']!=recipe['selection'] or metadata['unit']!=recipe['output_unit'] or metadata['history_mode']!=recipe['history_mode'] or metadata['history_policy']!=recipe['history_policy']:
        raise PublicationError('Published metadata differs from the exact recipe')
    view=store.resolve(metadata['source_view'])
    if view['body']['dataset']!=metadata['dataset']:raise PublicationError('Metadata dataset differs from SourceView')
    dataset=store.resolve(metadata['dataset'])
    source_policies={b['role']:b['artifact'] for b in metadata['source_policy_bindings']}
    for role in ('availability','revision','quality'):
        if source_policies.get(role)!=dataset['body'][role+'_policy']:raise PublicationError('Source policy differs from dataset definition')
    for role in ('selection','alignment'):
        if source_policies.get(role)!=view['body'][role+'_policy']:raise PublicationError('Source policy differs from SourceView definition')
    if not any(b['role']=='evaluation' and b['artifact']==recipe.get('evaluation_policy') for b in bindings):
        raise PublicationError('Publication requires the approved evaluation policy bound to its recipe')
    for binding in bindings:
        policy=store.resolve(binding['artifact'])
        if policy['record_type']!='policy_definition' or policy['body']['approval_state']!='approved':
            raise PublicationError('Publication has an unapproved policy dependency')
    output_lineages={r['id']:r for r in lineages}
    for row in rows:
        lineage=output_lineages[row['lineage']['id']]
        if reference(lineage)!=row['lineage'] or lineage['operation']!=reference(feature) or lineage['implementation']!=implementation_ref or lineage['policy_bindings']!=bindings:
            raise PublicationError('Output lineage dependency mismatch')
        roles={b['role']:b['artifact'] for b in lineage['inputs']}
        if set(roles)-{'numerator','denominator'} or row['status']=='valid' and set(roles)!={'numerator','denominator'}:
            raise PublicationError('Output has invalid operand roles')
        contexts={}
        for role,binding in roles.items():
            locator=store.resolve_operand(binding);body=locator['record']['body'];context=body['key']
            if body['pit_snapshot'] not in source_snapshots:raise PublicationError('Operand snapshot is not pinned in this materialization')
            if body['dataset']!=metadata['dataset'] or body['source_view']!=metadata['source_view'] or {k:context[k] for k in ('measure','entity_id','dimensions')}!=metadata['selection']:
                raise PublicationError('Output operand crosses a source partition')
            if context['available_at']>row['evaluation_cutoff'] or context['reference_time']>row['evaluation_cutoff']:
                raise PublicationError('Operand was unavailable at output cutoff')
            if role=='numerator' and context['reference_time']!=row['reference_time']:
                raise PublicationError('Numerator reference period differs from output')
            native=store._native_rows[body['pit_snapshot']['id']];mapping=body['field_mapping']
            if role=='numerator':
                current=[r[mapping['reference_time']] for r in native if r[mapping['available_at']]<=row['evaluation_cutoff'] and r[mapping['reference_time']]<=row['evaluation_cutoff']]
                if not current or context['reference_time']!=max(current):raise PublicationError('Numerator is not the latest reference at the cutoff')
            eligible=[r for r in native if r[mapping['reference_time']]==context['reference_time'] and r[mapping['available_at']]<=row['evaluation_cutoff']]
            if not eligible or digest(max(eligible,key=lambda r:r[mapping['available_at']]))!=body['pit_row_sha256']:
                raise PublicationError('Operand is not the latest permitted vintage at its cutoff')
            contexts[role]=context
        if 'denominator' in contexts and metadata['cadence']['frequency']=='monthly':
            current=contexts['numerator']['reference_time'];previous=contexts['denominator']['reference_time']
            year,month=map(int,current[:7].split('-'));month-=1
            if month==0:year-=1;month=12
            if previous!=f'{year:04d}-{month:02d}-01':raise PublicationError('Denominator is not the immediately preceding calendar month')


def publish_feature(root, *, feature, input_series, result, metadata, operand_links,
                    operand_records, supporting_records, implementation, policy_bindings,
                    interrupt_after=None):
    """Publish one already-computed feature with exact role-labelled operands.

    The caller must resolve approved source eligibility before execution. This
    layer independently validates dependencies, recipe identity and output schema.
    `interrupt_after` is an isolated-test fault injection boundary only.
    """
    store=FeatureStore(root);result=normalize_result(result)
    policy_bindings=normalize_bindings(policy_bindings)
    if feature['id']!=feature_id(feature['body']['recipe']) or feature['body']['signal_id']!=signal_id(feature['body']['recipe']):
        raise PublicationError('Feature/Signal identity differs from its recipe')
    if result['execution']['recipe']!=reference(feature):raise PublicationError('Computed recipe differs from published definition')
    if result['execution']['implementation']!=reference(implementation):raise PublicationError('Implementation evidence mismatch')
    if result['execution']['status']=='no_valid_output':raise PublicationError('An entirely invalid result cannot be published as a materialized feature')
    if len(operand_links)!=len(result['observations']):raise PublicationError('Missing operand lineage')
    index=[{k:row[k] for k in ('reference_time','evaluation_cutoff')} for row in result['observations']]
    input_key=execution_materialization_key(reference(feature),input_series,result['execution']['cutoffs'],reference(implementation),policy_bindings,output_index=index)
    mid=make_materialization_id_from_key(input_key)
    rows,lineages=[],[]
    for original,links in zip(result['observations'],operand_links):
        if set(links)-{'numerator','denominator'}:raise PublicationError('Unexpected operand role')
        if original['status']=='valid' and set(links)!={'numerator','denominator'}:raise PublicationError('Defined ratio requires both operands')
        inputs=[{'role':role,'artifact':binding} for role,binding in sorted(links.items())]
        lineage=_lineage(inputs,reference(feature),reference(implementation),policy_bindings)
        lineages.append(lineage)
        rows.append(dict(original,materialization_id=mid,lineage=reference(lineage)))
    counts={status:sum(r['status']==status for r in rows) for status in ('valid','missing','invalid')}
    row_bytes=b''.join(canonical_bytes(row)+b'\n' for row in rows)
    manifest={'schema_version':'0.3.0','record_type':'materialization_manifest','id':mid,'version':'1.0.0',
        'dataset_role':'feature','definition':reference(feature),'identity_profile':'transformation_execution.1.0.0',
        'input_key':input_key,'observation_schema_version':'0.3.0','metadata':metadata,'partitions':[],
        'row_count':len(rows),'status_counts':counts,'semantic_rows_sha256':semantic_rows_digest(rows),
        'lineage':sorted({r['id']:reference(r) for r in lineages}.values(),key=lambda r:r['id'])}
    with store.writer():
        existing=store.path(materialization_path(mid))
        if existing.exists():
            old=read_materialization(root,mid)
            if old['manifest']['input_key']!=input_key or old['observations']!=rows:
                raise PublicationError('Conflicting scientific output for an existing immutable materialization')
            entry=_publish_entry(store,feature,old['manifest'])
            return {'reused':True,'signal_id':feature['body']['signal_id'],'feature':reference(feature),'materialization':reference(old['manifest']),'entry':reference(entry)}
        # Install immutable dependency records; none makes a completed feature visible.
        for record in [*supporting_records,implementation,feature,*operand_records,*lineages]:store.install_record(record)
        store.verify_closure([feature,implementation,*operand_records,*lineages])
        _verify_outputs(store,feature,metadata,reference(implementation),policy_bindings,rows,lineages,input_key['source_snapshots'])
        if interrupt_after=='dependencies':raise InterruptedPublication('Interrupted before observation payload publication')
        member=store.io.blob(row_bytes,'jsonl','feature_observations',len(rows))
        keys=[_key(r) for r in rows]
        partition={**member,'partition_key':'P_'+digest({'entity_id':metadata['selection']['entity_id'],'output_index':index}),
                   'entity_id':metadata['selection']['entity_id'],'minimum_key':min(keys,key=lambda k:(k['entity_id'],k['evaluation_cutoff'],k['reference_time'] or '')),
                   'maximum_key':max(keys,key=lambda k:(k['entity_id'],k['evaluation_cutoff'],k['reference_time'] or ''))}
        manifest['partitions']=[partition]
        manifest=normalize_materialization(manifest,rows)
        store.verify_closure([manifest])
        if interrupt_after=='payloads':raise InterruptedPublication('Interrupted before materialization completion')
        store.install_record(manifest)
        if interrupt_after=='manifest':raise InterruptedPublication('Interrupted before Signal Library projection')
        # An entry can only link a freshly re-read and verified durable manifest.
        verified=read_materialization(root,mid)
        entry=_publish_entry(store,feature,verified['manifest'])
    return {'reused':False,'signal_id':feature['body']['signal_id'],'feature':reference(feature),'materialization':reference(manifest),'entry':reference(entry)}


def _publish_entry(store, feature, manifest):
    sid=feature['body']['signal_id']
    candidates=[]
    folder=store.path('storage/catalog/signal_library/entries/'+sid)
    for path in sorted(folder.glob('*.json')):
        old=strict_json(stable_read(path));normalize_library_entry(old)
        if path.name!=digest(old)+'.json':raise PublicationError('Library entry filename mismatch')
        if old['feature']!=reference(feature):raise PublicationError('Signal resolves to another Feature')
        candidates.append(old)
    materializations={reference(manifest)['id']:reference(manifest)}
    for old in candidates:
        for ref in old['feature_materializations']:materializations[ref['id']]=ref
    refs=sorted(materializations.values(),key=lambda r:r['id'])
    for old in candidates:
        if old['feature_materializations']==refs:return old
    entry={'schema_version':'0.3.0','record_type':'signal_library_entry','version':'1.0.0','signal_id':sid,
           'feature':reference(feature),'relationship_results':[],'feature_materializations':refs,'supersedes':None}
    entry['id']='LIBRARYENTRY_'+digest(entry)
    normalize_library_entry(entry)
    store.verify_closure([entry]);store.install_record(entry)
    return entry


def read_materialization(root, identifier, *, research=False):
    """Fresh independent read, with payload/schema/reference/operand verification."""
    store=FeatureStore(root)
    manifest=strict_json(stable_read(store.path(materialization_path(identifier))))
    if manifest.get('schema_version')=='0.6.0':
        from data.fx_feature_store import read_fx_materialization
        return read_fx_materialization(root,identifier,research=research)
    normalize_materialization(manifest)
    if manifest['id']!=identifier:raise PublicationError('Manifest path identity mismatch')
    rows=[]
    for partition in manifest['partitions']:
        data=store.payload(partition)
        selected=[strict_json(line) for line in data.splitlines()]
        if data!=b''.join(canonical_bytes(row)+b'\n' for row in selected):raise PublicationError('Noncanonical observation payload')
        if len(selected)!=partition['row_count']:raise PublicationError('Partition row count mismatch')
        rows.extend(selected)
    normalize_materialization(manifest,rows)
    store.verify_closure([manifest])
    feature=store.resolve(manifest['definition'])
    if feature['id']!=feature_id(feature['body']['recipe']):raise PublicationError('Stored recipe identity mismatch')
    lineage_records=[store.resolve(binding) for binding in manifest['lineage']]
    _verify_outputs(store,feature,manifest['metadata'],manifest['input_key']['implementation'],manifest['input_key']['policy_bindings'],rows,lineage_records,manifest['input_key']['source_snapshots'])
    operands={}
    for row in rows:
        lineage=store.resolve(row['lineage'])
        if lineage['operation']!=manifest['definition'] or lineage['implementation']!=manifest['input_key']['implementation']:
            raise PublicationError('Output lineage recipe/implementation mismatch')
        roles={binding['role']:binding['artifact'] for binding in lineage['inputs']}
        if row['status']=='valid' and set(roles)!={'numerator','denominator'}:raise PublicationError('Missing exact operand roles')
        for role,binding in roles.items():
            locator=store.resolve_operand(binding)
            context=locator['record']['body']['key']
            if context['available_at']>row['evaluation_cutoff'] or context['reference_time']>row['evaluation_cutoff']:
                raise PublicationError('Operand was unavailable at output cutoff')
            if role=='numerator' and context['reference_time']!=row['reference_time']:
                raise PublicationError('Numerator reference period differs from output')
            operands[binding['id']]=locator
    return {'feature':feature,'manifest':manifest,'observations':rows,'operands':operands,
            'metadata':{'dataset':store.resolve(manifest['metadata']['dataset']),
                        'source_view':store.resolve(manifest['metadata']['source_view'])}}


def retrieve_signal(root, signal_id, materialization_id=None):
    """Resolve the canonical Signal projection; no provider-specific knowledge."""
    token(signal_id)
    if not signal_id.startswith('SIGNAL_'):raise PublicationError('Wrong Signal ID')
    store=FeatureStore(root);entries=[]
    for path in sorted(store.path('storage/catalog/signal_library/entries/'+signal_id).glob('*.json')):
        entry=strict_json(stable_read(path));normalize_library_entry(entry)
        if entry['signal_id']!=signal_id or path.name!=digest(entry)+'.json':raise PublicationError('Invalid Signal projection')
        entries.append(entry)
    if not entries:raise PublicationError('No completed stored Signal projection')
    features={canonical_bytes(e['feature']):e['feature'] for e in entries}
    if len(features)!=1:raise PublicationError('Conflicting Feature definitions under one Signal')
    refs={r['id']:r for entry in entries for r in entry['feature_materializations']}
    if materialization_id is None:
        if len(refs)!=1:raise PublicationError('Select an explicit materialization ID')
        materialization_id=next(iter(refs))
    if materialization_id not in refs:raise PublicationError('Materialization is not linked to this Signal')
    result=read_materialization(root,materialization_id)
    if reference(result['manifest'])!=refs[materialization_id] or result['feature']['body']['signal_id']!=signal_id or next(iter(features.values()))!=reference(result['feature']):
        raise PublicationError('Signal/Feature/materialization reference mismatch')
    if any(entry['relationship_results'] for entry in entries):raise PublicationError('Research-linked projections need the separate research reader')
    return dict(result,signal_id=signal_id,materialization_state='materialized',scientific_state='untested',library_entries=entries)
