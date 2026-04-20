import { NextRequest, NextResponse } from "next/server";
import { Resend } from "resend";

export async function POST(req: NextRequest) {
  const { name, email, message } = await req.json();

  if (!name || !email || !message) {
    return NextResponse.json({ error: "All fields are required." }, { status: 400 });
  }

  const apiKey = process.env.RESEND_API_KEY;
  if (!apiKey) {
    return NextResponse.json({ error: "Contact not configured." }, { status: 503 });
  }

  const resend = new Resend(apiKey);

  const { error } = await resend.emails.send({
    from: "trIAge Contact <onboarding@resend.dev>",
    to: "samuelpilotbasse@gmail.com",
    replyTo: email,
    subject: `trIAge — message from ${name}`,
    text: `Name: ${name}\nEmail: ${email}\n\n${message}`,
  });

  if (error) {
    return NextResponse.json({ error: "Failed to send message." }, { status: 500 });
  }

  return NextResponse.json({ ok: true });
}
