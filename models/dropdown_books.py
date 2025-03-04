import discord

book_data = {
    "Hamlet": {
        "title": "Hamlet",
        "description": "A story about prince Hamlet",
        "author": "William Shakespear",
        "borrowed": False,
        "published": 1612
    },
    "Romeo and Juliet": {
        "title": "Romeo and Juliet",
        "description": "A tragedy ",
        "author": "William Shakespear",
        "borrowed": False,
        "published": 1613
    }
}

class BookshelfDropdown(discord.ui.Select):
    def __init__(self, embed: discord.Embed):
        options = [
            discord.SelectOption(label='Hamlet', description='The tragedy of Hamlet', emoji='🟥'),
            discord.SelectOption(label='Macbeth', description='The tragedy of Macbeth', emoji='🟩'),
            discord.SelectOption(label='Romeo and Juliet', description='The tragedy of Romeo and Juliet', emoji='🟦',),
        ]
        self.embed = embed
        super().__init__(placeholder='Choose your favourite colour...', min_values=1, max_values=1, options=options)

    async def callback(self, interaction: discord.Interaction):
        book = book_data[self.values[0]]
        self.embed.clear_fields()
        self.embed.add_field(
            name="Title",
            value=f"**{book['title']} ([{book['published']}](https://discord.com))**"
        ).add_field(
            name="Author",
            value=book["author"]
        ).add_field(
            name="Available",
            value="Yes" if not book["borrowed"] else "No"
        ).add_field(
            name=book["description"],
            value=" "
        ).set_thumbnail(
            ""
        )
        await interaction.response.edit_message(embed=self.embed)


class BookshelfDropdownView(discord.ui.View):
    def __init__(self, embed: discord.Embed):
        super().__init__()
        self.add_item(BookshelfDropdown(embed))



