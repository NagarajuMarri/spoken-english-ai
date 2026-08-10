import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { api, ApiError } from "../api/client";
import { RouterProvider } from "../routes/router";
import { ConversationScreen } from "../screens/ExperienceScreens";
import { account, ananya } from "./fixtures";

class Recorder {
  static isTypeSupported=(type:string)=>type.startsWith("audio/webm");
  state:RecordingState="inactive";
  mimeType="audio/webm;codecs=opus";
  ondataavailable:((event:BlobEvent)=>void)|null=null;
  onerror:(()=>void)|null=null;
  onstop:(()=>void)|null=null;
  constructor(_stream:MediaStream,options?:MediaRecorderOptions){if(options?.mimeType)this.mimeType=options.mimeType}
  start(){this.state="recording"}
  stop(){
    this.state="inactive";
    this.ondataavailable?.({data:new Blob([new Uint8Array([1,2,3,4,5])],{type:this.mimeType})}as BlobEvent);
    this.onstop?.();
  }
}

const stream={getTracks:()=>[{stop:vi.fn()}]}as unknown as MediaStream;
const successfulTranscription={
  transcript:"I practise English every morning.",
  detected_language:"en",
  duration_ms:500,
  size_bytes:5,
};

beforeEach(()=>{
  Object.defineProperty(window,"isSecureContext",{configurable:true,value:true});
  Object.defineProperty(window,"MediaRecorder",{configurable:true,value:Recorder});
  Object.defineProperty(navigator,"mediaDevices",{configurable:true,value:{getUserMedia:vi.fn().mockResolvedValue(stream)}});
  Object.defineProperty(navigator,"permissions",{configurable:true,value:{query:vi.fn().mockResolvedValue({state:"prompt",addEventListener:vi.fn(),removeEventListener:vi.fn()})}});
  vi.spyOn(api,"conversation").mockResolvedValue({id:"conversation-voice"});
  vi.spyOn(api,"transcribe").mockResolvedValue(successfulTranscription);
  vi.spyOn(api,"turn").mockResolvedValue({turn_id:"voice-input-turn",tutor_message:"Thank you.",next_question:"What next?",vocabulary_suggestions:[]});
  vi.spyOn(api,"speech").mockRejectedValue(new Error("Audio is outside this STT-only test."));
});

describe("voice input customer journey",()=>{
  it("moves captured bytes through STT into visible learner text and the conversation pipeline",async()=>{
    render(<RouterProvider><ConversationScreen account={account} tutor={ananya} languageMode="ENGLISH"/></RouterProvider>);
    await waitFor(()=>expect(api.conversation).toHaveBeenCalled());
    await userEvent.click(screen.getByRole("checkbox",{name:/consent to voice processing/i}));
    await userEvent.click(screen.getByRole("button",{name:"Start microphone"}));
    expect(screen.getByText("Listening", { selector: "p" })).toBeInTheDocument();
    await waitFor(()=>expect(screen.getByLabelText(/tutor status: listening/)).toHaveAttribute("data-state", "LISTENING"));
    await userEvent.click(screen.getByRole("button",{name:"Stop and transcribe"}));
    await waitFor(()=>expect(api.transcribe).toHaveBeenCalledOnce());
    const capture=vi.mocked(api.transcribe).mock.calls[0][1];
    expect(capture.blob.size).toBeGreaterThan(0);
    expect(capture.blob.type).toContain("audio/webm");
    expect(await screen.findByLabelText("Latest recognized transcript")).toHaveTextContent("I practise English every morning.");
    expect(api.turn).toHaveBeenCalledWith(
      "conversation-voice",
      "I practise English every morning.",
      "ENGLISH",
      expect.any(String),
      { detectedLanguage: "en" },
    );
  });

  it("shows a safe STT error and does not submit an invented learner message",async()=>{
    vi.mocked(api.transcribe).mockRejectedValue(new ApiError(422,"No clear speech was detected."));
    render(<RouterProvider><ConversationScreen account={account} tutor={ananya} languageMode="ENGLISH"/></RouterProvider>);
    await waitFor(()=>expect(api.conversation).toHaveBeenCalled());
    await userEvent.click(screen.getByRole("checkbox",{name:/consent to voice processing/i}));
    await userEvent.click(screen.getByRole("button",{name:"Start microphone"}));
    await userEvent.click(screen.getByRole("button",{name:"Stop and transcribe"}));
    expect(await screen.findByRole("alert")).toHaveTextContent("No clear speech was detected.");
    expect(screen.queryByRole("button",{name:"Retry transcription"})).not.toBeInTheDocument();
    expect(screen.queryByRole("button",{name:"Discard recording"})).not.toBeInTheDocument();
    expect(api.turn).not.toHaveBeenCalled();
  });

  it.each([
    ["in-progress conflict", new ApiError(409,"This voice capture is still processing.","speech_to_text_in_progress",true)],
    ["provider unavailable", new ApiError(503,"Speech recognition is unavailable.","speech_to_text_unavailable",true)],
    ["provider timeout", new ApiError(504,"Speech recognition timed out.","speech_to_text_timeout",true)],
    ["network failure", new TypeError("Failed to fetch")],
  ])("retries the same retained capture and identity after a retryable %s",async(_label,error)=>{
    vi.mocked(api.transcribe)
      .mockRejectedValueOnce(error)
      .mockResolvedValueOnce(successfulTranscription);
    render(<RouterProvider><ConversationScreen account={account} tutor={ananya} languageMode="ENGLISH"/></RouterProvider>);
    await waitFor(()=>expect(api.conversation).toHaveBeenCalled());
    await userEvent.click(screen.getByRole("checkbox",{name:/consent to voice processing/i}));
    await userEvent.click(screen.getByRole("button",{name:"Start microphone"}));
    await userEvent.click(screen.getByRole("button",{name:"Stop and transcribe"}));
    expect(await screen.findByRole("alert")).toHaveTextContent(error.message);

    const firstCall=vi.mocked(api.transcribe).mock.calls[0];
    expect(firstCall[2]).toEqual(expect.any(String));
    await userEvent.click(screen.getByRole("button",{name:"Retry transcription"}));
    await waitFor(()=>expect(api.transcribe).toHaveBeenCalledTimes(2));
    const secondCall=vi.mocked(api.transcribe).mock.calls[1];
    expect(secondCall[1].blob).toBe(firstCall[1].blob);
    expect(secondCall[1].durationMs).toBe(firstCall[1].durationMs);
    expect(secondCall[2]).toBe(firstCall[2]);
    expect(await screen.findByLabelText("Latest recognized transcript")).toHaveTextContent(successfulTranscription.transcript);
    expect(screen.queryByRole("button",{name:"Retry transcription"})).not.toBeInTheDocument();
    expect(screen.queryByRole("button",{name:"Discard recording"})).not.toBeInTheDocument();
    expect(api.turn).toHaveBeenCalledOnce();
  });

  it("clears the retained capture when a retry receives a final rejection",async()=>{
    vi.mocked(api.transcribe)
      .mockRejectedValueOnce(new ApiError(504,"Speech recognition timed out.","speech_to_text_timeout",true))
      .mockRejectedValueOnce(new ApiError(422,"No clear speech was detected.","no_speech_detected",false));
    render(<RouterProvider><ConversationScreen account={account} tutor={ananya} languageMode="ENGLISH"/></RouterProvider>);
    await waitFor(()=>expect(api.conversation).toHaveBeenCalled());
    await userEvent.click(screen.getByRole("checkbox",{name:/consent to voice processing/i}));
    await userEvent.click(screen.getByRole("button",{name:"Start microphone"}));
    await userEvent.click(screen.getByRole("button",{name:"Stop and transcribe"}));
    await userEvent.click(await screen.findByRole("button",{name:"Retry transcription"}));
    await waitFor(()=>expect(screen.getByRole("alert")).toHaveTextContent("No clear speech was detected."));
    expect(screen.queryByRole("button",{name:"Retry transcription"})).not.toBeInTheDocument();
    expect(screen.queryByRole("button",{name:"Discard recording"})).not.toBeInTheDocument();
    expect(api.turn).not.toHaveBeenCalled();
  });

  it("discards retained audio explicitly before a fresh capture",async()=>{
    vi.mocked(api.transcribe)
      .mockRejectedValueOnce(new ApiError(503,"Speech recognition is unavailable.","speech_to_text_unavailable",true))
      .mockResolvedValueOnce(successfulTranscription);
    render(<RouterProvider><ConversationScreen account={account} tutor={ananya} languageMode="ENGLISH"/></RouterProvider>);
    await waitFor(()=>expect(api.conversation).toHaveBeenCalled());
    await userEvent.click(screen.getByRole("checkbox",{name:/consent to voice processing/i}));
    await userEvent.click(screen.getByRole("button",{name:"Start microphone"}));
    await userEvent.click(screen.getByRole("button",{name:"Stop and transcribe"}));
    await screen.findByRole("button",{name:"Retry transcription"});
    const firstCall=vi.mocked(api.transcribe).mock.calls[0];

    await userEvent.click(screen.getByRole("button",{name:"Discard recording"}));
    await waitFor(()=>expect(screen.queryByRole("button",{name:"Retry transcription"})).not.toBeInTheDocument());
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
    await userEvent.click(screen.getByRole("button",{name:"Start microphone"}));
    await userEvent.click(screen.getByRole("button",{name:"Stop and transcribe"}));
    await waitFor(()=>expect(api.transcribe).toHaveBeenCalledTimes(2));
    const freshCall=vi.mocked(api.transcribe).mock.calls[1];
    expect(freshCall[1].blob).not.toBe(firstCall[1].blob);
    expect(freshCall[2]).not.toBe(firstCall[2]);
  });
});
