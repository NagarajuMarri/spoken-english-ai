import { act, renderHook, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { useMicrophone } from "../voice/useMicrophone";

class Recorder {
  static isTypeSupported = (type:string) => type.startsWith("audio/webm");
  static emitBytes = true;
  state:RecordingState = "inactive";
  mimeType = "audio/webm;codecs=opus";
  ondataavailable:((event:BlobEvent)=>void)|null = null;
  onerror:(()=>void)|null = null;
  onstop:(()=>void)|null = null;
  constructor(_stream:MediaStream, options?:MediaRecorderOptions){if(options?.mimeType)this.mimeType=options.mimeType}
  start(){this.state="recording"}
  stop(){
    this.state="inactive";
    const data=new Blob(Recorder.emitBytes?[new Uint8Array([26,45,223,163,1,2,3,4])]:[],{type:this.mimeType});
    this.ondataavailable?.({data} as BlobEvent);
    this.onstop?.();
  }
}

const stopTrack=vi.fn();
const stream={getTracks:()=>[{stop:stopTrack}]}as unknown as MediaStream;

beforeEach(()=>{
  Recorder.emitBytes=true;
  stopTrack.mockClear();
  Object.defineProperty(window,"isSecureContext",{configurable:true,value:true});
  Object.defineProperty(window,"MediaRecorder",{configurable:true,value:Recorder});
  Object.defineProperty(navigator,"mediaDevices",{configurable:true,value:{getUserMedia:vi.fn().mockResolvedValue(stream)}});
  Object.defineProperty(navigator,"permissions",{configurable:true,value:{query:vi.fn().mockResolvedValue({state:"prompt",addEventListener:vi.fn(),removeEventListener:vi.fn()})}});
});

describe("microphone capture lifecycle",()=>{
  it("never starts without consent",async()=>{
    const{result}=renderHook(()=>useMicrophone(false));
    await act(()=>result.current.start());
    expect(result.current.state).toBe("error");
    expect(navigator.mediaDevices.getUserMedia).not.toHaveBeenCalled();
  });

  it("requests permission only after start",async()=>{
    const{result}=renderHook(()=>useMicrophone(true));
    expect(navigator.mediaDevices.getUserMedia).not.toHaveBeenCalled();
    await act(()=>result.current.start());
    expect(result.current.state).toBe("recording");
    expect(result.current.permission).toBe("granted");
  });

  it("produces non-empty audio bytes and completes processing",async()=>{
    const captured=vi.fn().mockResolvedValue(undefined);
    const{result}=renderHook(()=>useMicrophone(true,captured));
    await act(()=>result.current.start());
    act(()=>result.current.stop());
    await waitFor(()=>expect(result.current.state).toBe("ready"));
    expect(captured).toHaveBeenCalledOnce();
    const value=captured.mock.calls[0][0];
    expect(value.mimeType).toContain("audio/webm");
    expect(value.sizeBytes).toBeGreaterThan(0);
    expect(value.blob.size).toBe(value.sizeBytes);
    expect(stopTrack).toHaveBeenCalled();
  });

  it("handles denied permission",async()=>{
    vi.mocked(navigator.mediaDevices.getUserMedia).mockRejectedValue(new DOMException("denied","NotAllowedError"));
    const{result}=renderHook(()=>useMicrophone(true));
    await act(()=>result.current.start());
    expect(result.current.state).toBe("denied");
    expect(result.current.permission).toBe("denied");
  });

  it("cancels without delivering captured audio",async()=>{
    const captured=vi.fn();
    const{result}=renderHook(()=>useMicrophone(true,captured));
    await act(()=>result.current.start());
    act(()=>result.current.cancel());
    expect(result.current.state).toBe("cancelled");
    expect(captured).not.toHaveBeenCalled();
    expect(stopTrack).toHaveBeenCalled();
  });

  it("reports an empty capture as no speech",async()=>{
    Recorder.emitBytes=false;
    const captured=vi.fn();
    const{result}=renderHook(()=>useMicrophone(true,captured));
    await act(()=>result.current.start());
    act(()=>result.current.stop());
    await waitFor(()=>expect(result.current.state).toBe("no_speech"));
    expect(captured).not.toHaveBeenCalled();
  });

  it("withdrawn consent blocks a new recording",async()=>{
    const{result,rerender}=renderHook(({consent})=>useMicrophone(consent),{initialProps:{consent:true}});
    rerender({consent:false});
    await act(()=>result.current.start());
    expect(result.current.state).toBe("error");
  });
});
