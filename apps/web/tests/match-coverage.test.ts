import test from 'node:test';
import assert from 'node:assert/strict';
import {matchCoverage} from '../lib/match-coverage';
import type {JobMatchReport, MatchReportRequirementResult} from '../lib/contracts';
const item = {eligibilityStatus:'conditional', semanticVerdict:'not_matched', candidateCount:0, assessmentSource:'deterministic'} as MatchReportRequirementResult;
function report(items: MatchReportRequirementResult[]) {return {eligibility:'conditional',retrievalVersion:'evidence-retrieval-v2',requirementResults:items} as JobMatchReport;}
test('thirteen unrecalled requirements are pending, not thirteen capability failures',()=>{
 const result=matchCoverage(report(Array.from({length:13},()=>({...item}))));
 assert.equal(result.counts.pending,13); assert.equal(result.noCandidates,true);assert.equal(result.legacy,false);
 assert.equal(Object.values(result.counts).reduce((a,b)=>a+b,0),13);
});
test('five mutually exclusive groups, with hard conflict taking precedence',()=>{
 const result=matchCoverage(report([item,{...item,semanticVerdict:'matched'}, {...item,semanticVerdict:'partial'},
 {...item,candidateCount:2,assessmentSource:'provider'}, {...item,eligibilityStatus:'missing',semanticVerdict:'partial'}]));
 assert.deepEqual(result.counts,{supported:1,partial:1,uncovered:1,pending:1,conflict:1});assert.equal(result.noCandidates,false);
});
test('old reports with unknown provenance do not claim zero retrieval or model rejection',()=>{
 const result=matchCoverage({...report([{...item,candidateCount:undefined,assessmentSource:undefined}]),retrievalVersion:undefined});
 assert.equal(result.legacy,true);assert.equal(result.noCandidates,false);assert.equal(result.counts.pending,1);
});
