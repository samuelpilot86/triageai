import { NextRequest, NextResponse } from "next/server";

export async function POST(req: NextRequest) {
  const { name, email, message } = await req.json();

  if (!name || !email || !message) {
    return NextResponse.json({ error: "All fields are required." }, { status: 400 });
  }

  const accessKey = process.env.WEB3FORMS_KEY;
  if (!accessKey) {
    return NextResponse.json({ error: "Contact not configured." }, { status: 503 });
  }

  // Web3Forms — access_key is public by design (whitelist-based)
  const res = await fetch("https://api.web3forms.com/submit", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      access_key: accessKey,
      name,
      email,
      message,
      subject: `trIAge contact from ${name}`,
    }),
  });

  const data = await res.json();
  if (!data.success) {
    return NextResponse.json({ error: "Failed to send message." }, { status: 500 });
  }

  return NextResponse.json({ ok: true });
}
