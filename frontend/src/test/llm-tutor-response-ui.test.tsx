import {render,screen,waitFor} from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import {expect,it,vi} from "vitest";
import {api} from "../api/client";
import {RouterProvider} from "../routes/router";
import {ConversationScreen} from "../screens/ExperienceScreens";
import {account,ananya} from "./fixtures";

it("shows a provider-safe tutor failure and allows the learner to retry",async()=>{
  vi.spyOn(api,"conversation").mockResolvedValue({id:"conversation-1"});
  vi.spyOn(api,"turn").mockRejectedValue(new Error("The tutor took too long to respond. Please try again."));
  render(<RouterProvider><ConversationScreen account={account} tutor={ananya} telugu={false}/></RouterProvider>);
  await waitFor(()=>expect(api.conversation).toHaveBeenCalled());
  await userEvent.type(screen.getByLabelText("Your message"),"Please help me practise.");
  await userEvent.click(screen.getByRole("button",{name:"Send"}));
  expect(await screen.findByRole("alert")).toHaveTextContent("The tutor took too long to respond");
  expect(screen.getByLabelText("Your message")).toBeEnabled();
});
