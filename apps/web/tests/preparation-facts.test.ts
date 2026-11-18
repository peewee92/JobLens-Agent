import test from 'node:test';
import assert from 'node:assert/strict';
import {preparationFacts} from '../lib/preparation-facts';
import type {JobPreparationBundle} from '../lib/contracts';

test('single saved interview evidence can supply a resume highlight without reading current profile',()=>{
 const p = {interviewFacts:{items:[{requirementId:'r',requirementText:'Python',importance:'must_have',evidenceIds:['e'],evidenceSummaries:['确实保存的经历']}]}} as unknown as JobPreparationBundle;
 assert.equal(preparationFacts(p).evidenceSummaries.get('e'),'确实保存的经历');
});
test('several evidence IDs must not be paired with summaries by guessed array order',()=>{
 const p = {interviewFacts:{items:[{requirementId:'r',requirementText:'Python',importance:'must_have',evidenceIds:['e','f'],evidenceSummaries:['一段经历']}]}} as unknown as JobPreparationBundle;
 assert.equal(preparationFacts(p).evidenceSummaries.size,0);
});
