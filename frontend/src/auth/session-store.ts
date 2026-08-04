import type { TokenPair } from "../models";
const KEY="speakmate.session.v1";
export const sessionStore={
  read():TokenPair|null{try{const value=sessionStorage.getItem(KEY);return value?JSON.parse(value) as TokenPair:null}catch{return null}},
  write(tokens:TokenPair){sessionStorage.setItem(KEY,JSON.stringify(tokens))},
  clear(){sessionStorage.removeItem(KEY)},
};
