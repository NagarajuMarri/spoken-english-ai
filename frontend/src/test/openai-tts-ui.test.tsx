import{beforeEach,expect,it,vi}from"vitest";
import{fireEvent,render,screen,waitFor}from"@testing-library/react";
import userEvent from"@testing-library/user-event";
import{api}from"../api/client";
import type{AiTurn,TutorSpeech}from"../models";
import{RouterProvider}from"../routes/router";
import{ConversationScreen}from"../screens/ExperienceScreens";
import{TutorAudioPlayer}from"../voice/TutorAudioPlayer";
import{account,ananya}from"./fixtures";

const firstSpeech: TutorSpeech={blob:new Blob([new Uint8Array(64)],{type:"audio/mpeg"}),provider:"openai",model:"gpt-4o-mini-tts",voice:"marin",cacheStatus:"MISS",inputCharacters:48,providerRequests:1,usageClassification:"CHARACTERS_AND_BYTES_PROVIDER_TOKEN_USAGE_UNAVAILABLE"};
const secondSpeech: TutorSpeech={...firstSpeech,blob:new Blob([new Uint8Array(80)],{type:"audio/mpeg"}),voice:"cedar"};
let play:ReturnType<typeof vi.spyOn>;
let pause:ReturnType<typeof vi.spyOn>;
let load:ReturnType<typeof vi.spyOn>;

beforeEach(()=>{
 play=vi.spyOn(HTMLMediaElement.prototype,"play").mockResolvedValue(undefined);
 pause=vi.spyOn(HTMLMediaElement.prototype,"pause").mockImplementation(()=>undefined);
 load=vi.spyOn(HTMLMediaElement.prototype,"load").mockImplementation(()=>undefined);
 Object.defineProperty(URL,"createObjectURL",{configurable:true,value:vi.fn().mockReturnValueOnce("blob:first").mockReturnValueOnce("blob:second")});
 Object.defineProperty(URL,"revokeObjectURL",{configurable:true,value:vi.fn()});
});
it("plays valid OpenAI audio and exposes start end mute stop and replay controls",async()=>{
 render(<TutorAudioPlayer speech={firstSpeech} spokenText="You are improving. What happened next?" playbackId="turn-one" showDiagnostics/>);
 await waitFor(()=>expect(play).toHaveBeenCalledTimes(1));
 expect(screen.getByText(/Provider: openai · Model: gpt-4o-mini-tts · Voice: marin/)).toBeVisible();
 const player=screen.getByLabelText(/^Tutor voice audio/);
 fireEvent.play(player);
 expect(screen.getByRole("status")).toHaveTextContent("Tutor voice is playing");
 fireEvent.ended(player);
 expect(screen.getByRole("status")).toHaveTextContent("Tutor voice finished");
 await userEvent.click(screen.getByRole("button",{name:"Mute tutor voice"}));
 expect(player).toHaveProperty("muted",true);
 expect(screen.getByRole("button",{name:"Unmute tutor voice"})).toHaveAttribute("aria-pressed","true");
 await userEvent.click(screen.getByRole("button",{name:"Stop tutor voice"}));
 expect(pause).toHaveBeenCalled();
 expect(screen.getByRole("status")).toHaveTextContent("stopped");
 await userEvent.click(screen.getByRole("button",{name:"Replay tutor voice"}));
 expect(play).toHaveBeenCalledTimes(2);
 expect(load).toHaveBeenCalled();
});

it("handles Chrome autoplay blocking with an explicit user play path",async()=>{
 play.mockRejectedValueOnce(new DOMException("blocked","NotAllowedError")).mockResolvedValueOnce(undefined);
 render(<TutorAudioPlayer speech={firstSpeech} spokenText="Tutor response" playbackId="turn-one"/>);
 expect(await screen.findByRole("status")).toHaveTextContent("Chrome blocked autoplay");
 await userEvent.click(screen.getByRole("button",{name:"Play tutor voice"}));
 await waitFor(()=>expect(play).toHaveBeenCalledTimes(2));
});

it("cancels the prior source and plays the second consecutive response once",async()=>{
 const{rerender}=render(<TutorAudioPlayer speech={firstSpeech} spokenText="First response" playbackId="turn-one" showDiagnostics/>);
 await waitFor(()=>expect(play).toHaveBeenCalledTimes(1));
 rerender(<TutorAudioPlayer speech={secondSpeech} spokenText="Second response" playbackId="turn-two" showDiagnostics/>);
 await waitFor(()=>expect(play).toHaveBeenCalledTimes(2));
 expect(pause).toHaveBeenCalled();
 expect(URL.revokeObjectURL).toHaveBeenCalledWith("blob:first");
 expect(screen.getByText(/Voice: cedar/)).toBeVisible();
});

it("retrieves OpenAI speech for the exact visible tutor turn without browser synthesis fallback",async()=>{
 vi.spyOn(api,"conversation").mockResolvedValue({id:"conversation-feature-5"});
 vi.spyOn(api,"turn").mockResolvedValue({turn_id:"ai-turn-feature-5",tutor_message:"You are improving.",next_question:"What happened next?",vocabulary_suggestions:[]});
 vi.spyOn(api,"speech").mockResolvedValue(firstSpeech);
 const browserSpeak=vi.fn();
 Object.defineProperty(window,"speechSynthesis",{configurable:true,value:{speak:browserSpeak}});
 render(<RouterProvider><ConversationScreen account={account} tutor={ananya} languageMode="ENGLISH"/></RouterProvider>);
 await waitFor(()=>expect(api.conversation).toHaveBeenCalled());
 await userEvent.type(screen.getByLabelText("Your message"),"I studied today.");
 await userEvent.click(screen.getByRole("button",{name:"Send"}));
 expect(await screen.findByLabelText("Current tutor response")).toHaveTextContent("You are improving. What happened next?");
 expect(api.speech).toHaveBeenCalledWith("conversation-feature-5","ai-turn-feature-5");
  expect(screen.queryByText(/Provider: openai/)).not.toBeInTheDocument();
 expect(browserSpeak).not.toHaveBeenCalled();
});

it("does not silently skip TTS when a stale tutor response omits the turn identity",async()=>{
 const warning=vi.spyOn(console,"warn").mockImplementation(()=>undefined);
 vi.spyOn(api,"conversation").mockResolvedValue({id:"conversation-stale-shape"});
 vi.spyOn(api,"turn").mockResolvedValue({tutor_message:"The text response remains visible.",next_question:"Can you try again?",vocabulary_suggestions:[]} as unknown as AiTurn);
 const speechRequest=vi.spyOn(api,"speech");
 render(<RouterProvider><ConversationScreen account={account} tutor={ananya} languageMode="ENGLISH"/></RouterProvider>);
 await waitFor(()=>expect(api.conversation).toHaveBeenCalled());
 await userEvent.type(screen.getByLabelText("Your message"),"Hello tutor.");
 await userEvent.click(screen.getByRole("button",{name:"Send"}));
 expect(await screen.findByText(/The text response remains visible/)).toBeVisible();
  expect(await screen.findByRole("alert")).toHaveTextContent("Tutor voice is not ready for this response");
 expect(speechRequest).not.toHaveBeenCalled();
 expect(warning).toHaveBeenCalledWith("speakmate_tts_event",{event:"request_not_made",reason:"missing_turn_id"});
});

it("requests and plays audio after each of two consecutive tutor turns",async()=>{
 vi.spyOn(api,"conversation").mockResolvedValue({id:"conversation-two-turns"});
 vi.spyOn(api,"turn")
  .mockResolvedValueOnce({turn_id:"turn-one",tutor_message:"First tutor answer.",next_question:"First question?",vocabulary_suggestions:[]})
  .mockResolvedValueOnce({turn_id:"turn-two",tutor_message:"Second tutor answer.",next_question:"Second question?",vocabulary_suggestions:[]});
 const speechRequest=vi.spyOn(api,"speech")
  .mockResolvedValueOnce(firstSpeech)
  .mockResolvedValueOnce(secondSpeech);
 render(<RouterProvider><ConversationScreen account={account} tutor={ananya} languageMode="ENGLISH"/></RouterProvider>);
 await waitFor(()=>expect(api.conversation).toHaveBeenCalled());
 const input=screen.getByLabelText("Your message");
 await userEvent.type(input,"First learner turn.");
 await userEvent.click(screen.getByRole("button",{name:"Send"}));
 await waitFor(()=>expect(speechRequest).toHaveBeenNthCalledWith(1,"conversation-two-turns","turn-one"));
 await userEvent.type(input,"Second learner turn.");
 await userEvent.click(screen.getByRole("button",{name:"Send"}));
 await waitFor(()=>expect(speechRequest).toHaveBeenNthCalledWith(2,"conversation-two-turns","turn-two"));
 expect(speechRequest).toHaveBeenCalledTimes(2);
 expect(play).toHaveBeenCalledTimes(2);
  expect(screen.queryByText(/Voice: cedar/)).not.toBeInTheDocument();
  expect(screen.getByLabelText("Current tutor response")).toHaveTextContent("Second tutor answer. Second question?");
});

it("keeps tutor text usable when TTS fails and offers an explicit audio-only retry",async()=>{
 vi.spyOn(api,"conversation").mockResolvedValue({id:"conversation-feature-5-error"});
 vi.spyOn(api,"turn").mockResolvedValue({turn_id:"ai-turn-feature-5-error",tutor_message:"Your text answer is safe.",next_question:"Would you like to retry audio?",vocabulary_suggestions:[]});
 vi.spyOn(api,"speech").mockRejectedValueOnce(new Error("Tutor voice timed out. Try audio again.")).mockResolvedValueOnce(firstSpeech);
 render(<RouterProvider><ConversationScreen account={account} tutor={ananya} languageMode="ENGLISH"/></RouterProvider>);
 await waitFor(()=>expect(api.conversation).toHaveBeenCalled());
 await userEvent.type(screen.getByLabelText("Your message"),"Hello tutor.");
 await userEvent.click(screen.getByRole("button",{name:"Send"}));
 expect(await screen.findByText(/Your text answer is safe/)).toBeVisible();
 expect(await screen.findByRole("alert")).toHaveTextContent("Tutor voice timed out");
 expect(screen.getByLabelText("Your message")).toBeEnabled();
  await userEvent.click(screen.getByRole("button",{name:"Retry tutor voice"}));
  await waitFor(()=>expect(api.speech).toHaveBeenCalledTimes(2));
  expect(screen.queryByText(/Provider: openai/)).not.toBeInTheDocument();
 expect(api.turn).toHaveBeenCalledTimes(1);
 expect(api.speech).toHaveBeenCalledTimes(2);
});
